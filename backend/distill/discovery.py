"""Find videos from channels I don't follow yet. Runs inside `distill ingest`; each source
has its own schedule so ingest can run often without burning quota.

Sources: saved searches (config/discovery.yaml), Hacker News, channels linked or featured by
videos I liked or watched past halfway, and weekly channel ideas from the LLM. New channels
are added as unreviewed candidates; their videos go through the strict discovery rules.
"""
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
import yaml

from distill.config import ROOT, Settings, settings as default_settings
from distill.youtube import YouTube

log = logging.getLogger(__name__)

SEARCHES_PATH = ROOT / "config" / "discovery.yaml"
HN_API = "https://hn.algolia.com/api/v1/search_by_date"
VIDEO_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^ ]*&)?v=|live/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})")
CHANNEL_URL_RE = re.compile(r"youtube\.com/channel/(UC[A-Za-z0-9_-]{22})")
HANDLE_URL_RE = re.compile(r"youtube\.com/@([A-Za-z0-9._-]{3,30})")
SEARCH_WINDOW_DAYS = 7
UPLOADS_PER_CHANNEL = 3
SEED_WINDOW_DAYS = 30


@dataclass
class DiscoverResult:
    searches: int = 0
    hn_stories: int = 0
    seeds: int = 0
    llm_channels: int = 0
    new_channels: int = 0
    new_videos: int = 0
    errors: int = 0
    # video id -> (source, via), gathered before anything is written
    found: dict[str, tuple[str, str]] = field(default_factory=dict)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _due(conn, key: str, every_h: float, now: datetime) -> bool:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return not row or datetime.fromisoformat(row[0]) <= now - timedelta(hours=every_h)


def _mark(conn, key: str, now: datetime) -> None:
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, now.isoformat()))


def _tier(conn, channel_id: str) -> str | None:
    row = conn.execute("SELECT tier, reviewed FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if not row:
        return None
    return row["tier"] if row["reviewed"] or row["tier"] != "candidate" else "unreviewed"


def discover(conn: sqlite3.Connection, yt: YouTube, s: Settings = default_settings, *,
             http: httpx.Client | None = None, llm=None, now: datetime | None = None) -> DiscoverResult:
    now = now or datetime.now(timezone.utc)
    res = DiscoverResult()
    http = http or httpx.Client(timeout=20)
    steps = [
        ("discovery:search", s.discovery_search_every_h, lambda: _searches(conn, yt, s, now, res)),
        ("discovery:hn", s.discovery_hn_every_h, lambda: _hacker_news(http, s, now, res)),
        ("discovery:adjacent", 0, lambda: _adjacent(conn, yt, s, now, res)),
    ]
    if llm is not None:
        steps.append(("discovery:llm", s.discovery_llm_every_days * 24,
                      lambda: _llm_channels(conn, yt, llm, s, now, res)))
    for key, every_h, run in steps:
        if not _due(conn, key, every_h, now):
            continue
        try:
            run()
            _mark(conn, key, now)
        except Exception as e:  # one failing source shouldn't stop the others
            log.warning("%s failed: %s", key, e)
            res.errors += 1
        conn.commit()  # don't hold the write lock across the next source's network calls
    _add(conn, yt, s, now, res)
    conn.commit()
    return res


def _searches(conn, yt: YouTube, s: Settings, now: datetime, res: DiscoverResult) -> None:
    queries = (yaml.safe_load(SEARCHES_PATH.read_text()) or {}).get("searches") or []
    last = {r["key"].removeprefix("search:"): r["value"] for r in conn.execute(
        "SELECT key, value FROM meta WHERE key LIKE 'search:%'")}
    # Least recently run first, so a long list rotates through over several runs.
    queries = sorted(queries, key=lambda q: last.get(q, ""))[:s.discovery_searches_per_run]
    after = _iso(now - timedelta(days=SEARCH_WINDOW_DAYS))
    for q in queries:
        for v in yt.search(q, after):
            res.found.setdefault(v["id"], ("search", q))
        _mark(conn, f"search:{q}", now)
        conn.commit()
        res.searches += 1


def _hacker_news(http: httpx.Client, s: Settings, now: datetime, res: DiscoverResult) -> None:
    since = int((now - timedelta(days=7)).timestamp())
    for query in ("youtube.com", "youtu.be"):
        r = http.get(HN_API, params={
            "query": query, "tags": "story", "hitsPerPage": 100,
            "numericFilters": f"points>={s.discovery_hn_min_points},created_at_i>{since}"})
        r.raise_for_status()
        for hit in r.json().get("hits", []):
            m = VIDEO_URL_RE.search(hit.get("url") or "")
            if m:
                res.found.setdefault(m.group(1), ("hn", f"Hacker News: {hit.get('title', '')}"[:200]))
                res.hn_stories += 1


def _adjacent(conn, yt: YouTube, s: Settings, now: datetime, res: DiscoverResult) -> None:
    """Channels a liked or half-watched video links to, plus the ones its channel features."""
    since = (now - timedelta(days=SEED_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    seeds = conn.execute(
        "SELECT v.id, v.description, v.channel_id, c.title AS channel_title FROM videos v "
        "JOIN channels c ON c.id = v.channel_id "
        "WHERE v.id NOT IN (SELECT video_id FROM discovery_seeds) AND ("
        "  v.id IN (SELECT video_id FROM progress WHERE watched_pct >= 50 AND last_watched_at >= ?)"
        "  OR v.id IN (SELECT video_id FROM feedback f WHERE signal = 'up' AND value != 'clear' AND created_at >= ? "
        "    AND id = (SELECT MAX(id) FROM feedback WHERE video_id = f.video_id AND signal IN ('up', 'down')))"
        ")", (since, since)).fetchall()
    budget = s.discovery_adjacent_channels_per_run
    for seed in seeds:
        if budget <= 0:
            break
        found = set(CHANNEL_URL_RE.findall(seed["description"] or ""))
        for handle in sorted(set(HANDLE_URL_RE.findall(seed["description"] or "")))[:5]:
            ch = yt.channel_by_handle(handle)
            if ch:
                found.add(ch["id"])
        featured_key = f"featured:{seed['channel_id']}"
        if _due(conn, featured_key, 24 * 30, now):
            found.update(yt.featured_channels(seed["channel_id"]))
            _mark(conn, featured_key, now)
            conn.commit()
        for channel_id in found - {seed["channel_id"]}:
            if budget <= 0:
                break
            if _tier(conn, channel_id) in ("trusted", "mixed", "blocked"):
                continue  # followed channels are ingested anyway
            budget -= 1
            _recent_uploads(yt, channel_id, s, now, res, "adjacent",
                            f"linked from {seed['channel_title']}")
        conn.execute("INSERT OR IGNORE INTO discovery_seeds (video_id) VALUES (?)", (seed["id"],))
        conn.commit()
        res.seeds += 1


def _recent_uploads(yt: YouTube, channel_id: str, s: Settings, now: datetime,
                    res: DiscoverResult, source: str, via: str) -> None:
    cutoff = _iso(now - timedelta(days=s.discovery_max_age_days))
    try:
        uploads = yt.channel_uploads(channel_id)
    except Exception as e:
        log.warning("RSS failed for %s: %s", channel_id, e)
        return
    fresh = [u for u in uploads if not u["is_short"] and (u["published_at"] or "") >= cutoff]
    for u in fresh[:UPLOADS_PER_CHANNEL]:
        res.found.setdefault(u["id"], (source, via))


LLM_SCHEMA = {
    "type": "object",
    "properties": {"channels": {"type": "array", "items": {
        "type": "object",
        "properties": {"handle": {"type": "string"}, "why": {"type": "string"}},
        "required": ["handle", "why"], "additionalProperties": False}}},
    "required": ["channels"],
    "additionalProperties": False,
}


def _llm_channels(conn, yt: YouTube, llm, s: Settings, now: datetime, res: DiscoverResult) -> None:
    from distill.classify import TASTE_PATH, _record_usage, month_spend  # classify imports ingest
    if month_spend(conn) >= s.llm_monthly_budget_usd:
        return
    follows = [r[0] for r in conn.execute(
        "SELECT title FROM channels WHERE tier IN ('trusted', 'mixed') ORDER BY watch_count DESC LIMIT 80")]
    prompt = (
        "Suggest 15 YouTube channels this viewer would likely enjoy but doesn't follow yet. "
        "Prefer active channels that post long-form videos; avoid clip, reaction and reupload channels. "
        "Give each channel's exact @handle and a short reason.\n\n"
        f"What they like:\n{TASTE_PATH.read_text().strip()}\n\n"
        f"Channels they already follow:\n" + "\n".join(f"- {t}" for t in follows))
    message = llm.messages.create(
        model=s.llm_model, max_tokens=2000, thinking={"type": "disabled"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": LLM_SCHEMA}},
        messages=[{"role": "user", "content": prompt}])
    _record_usage(conn, message.usage, s, batch=False)
    text = next((b.text for b in message.content if b.type == "text"), "{}")
    for idea in json.loads(text).get("channels", []):
        ch = yt.channel_by_handle(idea["handle"])  # suggestions can be made up; keep real ones only
        if not ch or _tier(conn, ch["id"]) in ("trusted", "mixed", "blocked"):
            continue
        conn.execute("INSERT OR IGNORE INTO channels (id, title, handle, thumb_url, source) "
                     "VALUES (?, ?, ?, ?, 'discovery')", (ch["id"], ch["title"], ch["handle"], ch["thumb_url"]))
        conn.commit()
        res.llm_channels += 1
        _recent_uploads(yt, ch["id"], s, now, res, "llm", f"suggested: {idea['why']}"[:200])


def _add(conn, yt: YouTube, s: Settings, now: datetime, res: DiscoverResult) -> None:
    """Look up everything found (1 unit per 50) and add what's new; ingest fills in the rest."""
    known = {r[0] for r in conn.execute("SELECT id FROM videos")}
    ids = [i for i in res.found if i not in known]
    if not ids:
        return
    cutoff = _iso(now - timedelta(days=s.discovery_max_age_days))
    for vid, d in yt.video_details(ids).items():
        source, via = res.found[vid]
        # HN links are often older talks; their age is when they were posted, not uploaded.
        if source != "hn" and (d["published_at"] or "") < cutoff:
            continue
        tier = _tier(conn, d["channel_id"])
        if tier == "blocked":
            continue
        if tier is None:
            conn.execute("INSERT INTO channels (id, title, source) VALUES (?, ?, 'discovery')",
                         (d["channel_id"], d["channel_title"] or d["channel_id"]))
            res.new_channels += 1
        conn.execute(
            "INSERT OR IGNORE INTO videos (id, channel_id, title, published_at, source, discovered_via) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (vid, d["channel_id"], d["title"], d["published_at"], source, via))
        res.new_videos += 1
