"""Classify mixed-channel videos with the LLM. It only describes each video; rules.yaml decides.

Small runs call the Messages API directly; larger ones go through the Batch API at half price.
Every call is metered into llm_usage, and nothing is sent once the monthly budget is spent.
"""
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from distill.config import ROOT, Settings, settings as default_settings
from distill.ingest import apply_rules

log = logging.getLogger(__name__)

PROMPT_VERSION = "v4"
TASTE_PATH = ROOT / "config" / "taste.md"
MAX_TOKENS = 400
# Conservative per-video estimate used to keep a run inside the remaining budget.
EST_COST_PER_VIDEO = 0.0006
EXAMPLES = 20

CATEGORIES = ["tech_ai", "sports", "gaming", "talks_podcasts", "learning", "fitness", "other"]
FORMATS = ["full_game", "highlights", "analysis", "reaction", "podcast", "interview", "talk",
           "tutorial", "course", "documentary", "news", "vlog", "compilation", "commentary",
           "gameplay", "other"]
SLOP_SIGNALS = ["ai_voiceover", "reupload", "listicle", "rage_bait", "misleading_title",
                "drama_gossip", "filler"]

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "topic": {"type": "string"},
        "format": {"type": "string", "enum": FORMATS},
        "clickbait": {"type": "boolean"},
        "substance": {"type": "string", "enum": ["low", "medium", "high"]},
        "slop_signals": {"type": "array", "items": {"type": "string", "enum": SLOP_SIGNALS}},
        "interest_match": {"type": "string", "enum": ["none", "some", "strong"]},
        "one_line": {"type": "string"},
        "english": {"type": "boolean"},
    },
    "required": ["category", "topic", "format", "clickbait", "substance", "slop_signals",
                 "interest_match", "one_line", "english"],
    "additionalProperties": False,
}

INSTRUCTIONS = """\
You sort YouTube videos for one person's private feed, which replaces the YouTube homepage.
For each video you get its metadata (title, channel, description, duration, tags, counts) and
describe it. You do not decide whether it's shown: separate rules do that from your answer,
so describe the video accurately rather than generously or harshly.

Fields:
- category: the main subject. talks_podcasts is for conversations and talks whatever the subject
  is not one of the others; use tech_ai, sports or gaming when the subject is clearly one of those.
- topic: a few words, specific (e.g. "Rockets vs Lakers", "Claude Code subagents", "VCT Champions final").
- format: what the video is. reaction = mostly someone watching and reacting to other content.
  compilation = clips stitched together with little added. commentary = one person's opinions on
  news or events. gameplay = playing a game, with or without commentary.
- clickbait: true when the title or description promises more than the video likely delivers
  (exaggerated stakes, withheld key fact, ALL CAPS shock framing). A punchy but accurate title is not clickbait.
- substance: how much real content there is for its length. Entertainment counts: a full game,
  a well-produced highlight package or a skilled gameplay video can be high substance.
- slop_signals: usually an empty list. Add one only with clear evidence, not from style alone
  (caps, emoji, streamer slang and hype are normal YouTube titles):
  ai_voiceover = text-to-speech narration or AI-generated faceless content; reupload = someone
  else's content posted again; listicle = a ranked list padded to length; rage_bait = built to
  provoke outrage at someone; misleading_title = the title misstates what happens;
  drama_gossip = about creators' or athletes' personal drama rather than their work or play;
  filler = stretched or repeated content with little in it.
- interest_match: each message says whether the viewer follows the channel.
  Followed channels are marked "mixed": some of their videos are worth watching, some aren't, so
  the channel's usual subject already interests them even if it isn't in the list below; the
  message says what they have watched from it. strong = squarely in a strong interest below, or
  very like what they watch from this channel; some = a typical video for the channel; none =
  off from what they watch it for, or "Not for me".
  Channels the viewer doesn't follow were found by discovery; judge those against the interests
  below only. strong = squarely in a strong interest; some = adjacent; none = outside them.
- one_line: plain words, under 20 words, saying what the video actually is. No hype. Always in English.
- english: true if the video itself is in English (judge by the title and description language).

The viewer's interests:

{taste}
"""


@dataclass
class ClassifyResult:
    collected: int = 0
    classified: int = 0
    errors: int = 0
    submitted_batch: str | None = None
    pending_batch: int = 0
    skipped_budget: int = 0
    visible: int = 0


def _client():
    import anthropic  # imported lazily so the rest of the app works without the key
    return anthropic.Anthropic()


def system_prompt(conn: sqlite3.Connection) -> str:
    text = INSTRUCTIONS.format(taste=TASTE_PATH.read_text().strip())
    # Latest label per video: Show anyway / 👍 = wanted, Hide this / Not interested / 👎 = not.
    examples = conn.execute(
        "SELECT v.title, c.title AS channel, "
        "CASE WHEN f.value = 'show' OR f.signal = 'up' THEN 'show' ELSE 'hide' END AS value "
        "FROM feedback f JOIN videos v ON v.id = f.video_id JOIN channels c ON c.id = v.channel_id "
        "WHERE f.value != 'clear' AND f.id = (SELECT MAX(id) FROM feedback WHERE video_id = f.video_id "
        "  AND signal IN ('override', 'up', 'down')) "
        "ORDER BY f.id DESC LIMIT ?", (EXAMPLES,)
    ).fetchall()
    if examples:
        text += ("\nVideos the viewer rated or corrected by hand (\"wanted\" = they liked it or chose "
                 "to see it, \"not wanted\" = they disliked or hid it). Use them to calibrate interest_match:\n")
        text += "\n".join(f"- {'wanted' if e['value'] == 'show' else 'not wanted'}: "
                          f"\"{e['title']}\" ({e['channel']})" for e in examples)
    return text


def watched_titles(conn: sqlite3.Connection, channel_id: str, n: int = 6) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT title FROM takeout_history WHERE channel_id = ? AND title IS NOT NULL "
        "GROUP BY title ORDER BY MAX(watched_at) DESC LIMIT ?", (channel_id, n))]


def video_message(v: sqlite3.Row | dict, watched: list[str] = ()) -> str:
    tags = ", ".join(json.loads(v["tags_json"] or "[]")[:15])
    mins, secs = divmod(v["duration_s"] or 0, 60)
    parts = [
        f"Channel: {v['channel_title']}",
        f"Title: {v['title']}",
        f"Published: {v['published_at'][:10]} · Duration: {mins}:{secs:02d}"
        f" · Views: {v['views'] or 'unknown'} · Likes: {v['likes'] or 'unknown'}",
    ]
    if tags:
        parts.append(f"Tags: {tags}")
    parts.append("Description:\n" + ((v["description"] or "").strip()[:1500] or "(none)"))
    if v["tier"] == "candidate":
        parts.append(f"The viewer doesn't follow this channel. Discovery found it ({v['discovered_via'] or v['source']}).")
        if watched:
            parts.append("They have watched a few of its videos before:\n" + "\n".join(f"- {t}" for t in watched))
    elif watched:
        parts.append(f"The viewer follows this channel and has watched {v['watch_count']} of its videos, recently:\n"
                     + "\n".join(f"- {t}" for t in watched))
    else:
        parts.append("The viewer follows this channel but has no watch history with it.")
    return "\n".join(parts)


def request_params(system: str, v: sqlite3.Row, s: Settings, watched: list[str] = ()) -> dict:
    return {
        "model": s.llm_model,
        "max_tokens": MAX_TOKENS,
        # Describing metadata doesn't need reasoning, and thinking tokens bill as output.
        "thinking": {"type": "disabled"},
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": video_message(v, watched)}],
    }


def month_spend(conn: sqlite3.Connection) -> float:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE date LIKE ?",
                        (f"{month}-%",)).fetchone()[0]


def _record_usage(conn, usage, s: Settings, batch: bool) -> None:
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    p_in, p_out = s.llm_price_input_per_mtok, s.llm_price_output_per_mtok
    cost = (usage.input_tokens * p_in + usage.output_tokens * p_out
            + cache_read * p_in * 0.1 + cache_write * p_in * 1.25) / 1e6
    if batch:
        cost /= 2
    conn.execute(
        "INSERT INTO llm_usage (date, requests, input_tokens, output_tokens, cache_read_tokens, "
        "cache_write_tokens, cost_usd) VALUES (date('now'), 1, ?, ?, ?, ?, ?) "
        "ON CONFLICT(date) DO UPDATE SET requests = requests + 1, "
        "input_tokens = input_tokens + excluded.input_tokens, "
        "output_tokens = output_tokens + excluded.output_tokens, "
        "cache_read_tokens = cache_read_tokens + excluded.cache_read_tokens, "
        "cache_write_tokens = cache_write_tokens + excluded.cache_write_tokens, "
        "cost_usd = cost_usd + excluded.cost_usd",
        (usage.input_tokens, usage.output_tokens, cache_read, cache_write, cost),
    )


def _store(conn, video_id: str, message, s: Settings) -> bool:
    """Save one response. Returns False if it's an error row."""
    error, data = None, None
    if message.stop_reason == "refusal":
        error = "refusal"
    elif message.stop_reason == "max_tokens":
        error = "max_tokens"
    else:
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            error = "bad_json"
    _store_row(conn, video_id, data, error, s)
    return error is None


def _store_row(conn, video_id: str, data: dict | None, error: str | None, s: Settings) -> None:
    d = data or {}
    conn.execute(
        "INSERT OR REPLACE INTO classifications (video_id, category, topic, format, clickbait, "
        "substance, slop_signals_json, interest_match, one_line, english, error, model, prompt_version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (video_id, d.get("category"), d.get("topic"), d.get("format"),
         None if data is None else int(bool(d.get("clickbait"))), d.get("substance"),
         None if data is None else json.dumps(d.get("slop_signals") or []),
         d.get("interest_match"), d.get("one_line"),
         None if data is None else int(d.get("english", True)), error, s.llm_model, PROMPT_VERSION),
    )


def pending_videos(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Videos the hard rules passed to the LLM that have no classification from the current
    prompt (so a PROMPT_VERSION bump reclassifies) and aren't already waiting in a batch."""
    return conn.execute(
        "SELECT v.*, c.title AS channel_title, c.watch_count, c.tier FROM videos v "
        "JOIN channels c ON c.id = v.channel_id JOIN decisions d ON d.video_id = v.id "
        "LEFT JOIN classifications cl ON cl.video_id = v.id "
        "WHERE (d.reason IN ('pending_llm', 'llm_error') OR d.reason LIKE 'rule:%') AND d.overridden = 0 "
        "AND (cl.video_id IS NULL OR cl.prompt_version != ?) "
        "AND v.id NOT IN (SELECT bv.video_id FROM llm_batch_videos bv "
        "                 JOIN llm_batches b ON b.id = bv.batch_id WHERE b.status = 'in_progress') "
        "ORDER BY v.published_at DESC", (PROMPT_VERSION,)
    ).fetchall()


def collect_batches(conn, client, s: Settings, res: ClassifyResult) -> None:
    for (batch_id,) in conn.execute(
            "SELECT id FROM llm_batches WHERE status = 'in_progress'").fetchall():
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status != "ended":
            res.pending_batch += conn.execute(
                "SELECT COUNT(*) FROM llm_batch_videos WHERE batch_id = ?", (batch_id,)).fetchone()[0]
            continue
        for r in client.messages.batches.results(batch_id):
            if r.result.type == "succeeded":
                _record_usage(conn, r.result.message.usage, s, batch=True)
                ok = _store(conn, r.custom_id, r.result.message, s)
                res.classified += ok
                res.errors += not ok
            else:  # errored / expired / canceled: leave it pending for the next run
                log.warning("batch %s: %s %s", batch_id, r.custom_id, r.result.type)
                res.errors += 1
        conn.execute("UPDATE llm_batches SET status = 'ended' WHERE id = ?", (batch_id,))
        res.collected += 1
    conn.commit()


def classify(conn: sqlite3.Connection, client=None, s: Settings = default_settings, *,
             wait_s: float = 900, poll_s: float = 20, limit: int | None = None) -> ClassifyResult:
    client = client or _client()
    res = ClassifyResult()
    collect_batches(conn, client, s, res)

    todo = pending_videos(conn)[:limit]
    affordable = max(0, int((s.llm_monthly_budget_usd - month_spend(conn)) / EST_COST_PER_VIDEO))
    if len(todo) > affordable:
        res.skipped_budget = len(todo) - affordable
        todo = todo[:affordable]

    if todo:
        system = system_prompt(conn)
        if len(todo) >= s.llm_batch_threshold:
            _submit_batch(conn, client, system, todo, s, res)
        else:
            _classify_direct(conn, client, system, todo, s, res)

    deadline = time.monotonic() + wait_s
    while res.submitted_batch and time.monotonic() < deadline:
        time.sleep(poll_s)
        res.pending_batch = 0
        collect_batches(conn, client, s, res)
        if not res.pending_batch:
            break

    res.visible = apply_rules(conn, s)
    conn.commit()
    return res


def _classify_direct(conn, client, system, todo, s: Settings, res: ClassifyResult) -> None:
    import anthropic
    for v in todo:
        try:
            message = client.messages.create(
                **request_params(system, v, s, watched_titles(conn, v["channel_id"])))
        except anthropic.BadRequestError as e:
            log.warning("classify %s: %s", v["id"], e.message)
            _store_row(conn, v["id"], None, f"bad_request: {e.message}"[:300], s)
            res.errors += 1
            continue
        # Auth, rate limit and server errors stop the run; what's done so far is kept.
        _record_usage(conn, message.usage, s, batch=False)
        ok = _store(conn, v["id"], message, s)
        res.classified += ok
        res.errors += not ok
        conn.commit()


def evaluate(conn: sqlite3.Connection, labels: dict[str, bool] | None = None) -> dict:
    """How well rules.yaml + the stored classifications agree with labels (video_id -> wanted).
    Labels default to every Show anyway / Hide this override. Calls no LLM."""
    from distill.rules import decide_llm, load_llm_rules
    if labels is None:
        labels = {r["video_id"]: r["value"] == "show" for r in conn.execute(
            "SELECT video_id, value FROM feedback f WHERE signal = 'override' AND value != 'clear' "
            "AND id = (SELECT MAX(id) FROM feedback WHERE video_id = f.video_id AND signal = 'override')")}
    rules = load_llm_rules()
    out = {"labeled": len(labels), "unclassified": 0, "agree": 0, "wrongly_hidden": [], "wrongly_shown": []}
    for vid, wanted in labels.items():
        row = conn.execute(
            "SELECT cl.*, v.title, c.tier FROM classifications cl JOIN videos v ON v.id = cl.video_id "
            "JOIN channels c ON c.id = v.channel_id WHERE cl.video_id = ? AND cl.error IS NULL",
            (vid,)).fetchone()
        if not row:
            out["unclassified"] += 1
            continue
        cls = dict(row, clickbait=bool(row["clickbait"]), english=row["english"] != 0,
                   slop_signals=json.loads(row["slop_signals_json"] or "[]"))
        d = decide_llm(cls, rules)
        if d.visible == wanted:
            out["agree"] += 1
        else:
            out["wrongly_hidden" if wanted else "wrongly_shown"].append((row["title"], d.reason))
    return out


def _submit_batch(conn, client, system, todo, s: Settings, res: ClassifyResult) -> None:
    batch = client.messages.batches.create(requests=[
        {"custom_id": v["id"], "params": request_params(system, v, s, watched_titles(conn, v["channel_id"]))}
        for v in todo
    ])
    conn.execute("INSERT INTO llm_batches (id) VALUES (?)", (batch.id,))
    conn.executemany("INSERT INTO llm_batch_videos (batch_id, video_id) VALUES (?, ?)",
                     [(batch.id, v["id"]) for v in todo])
    conn.commit()
    res.submitted_batch = batch.id
    res.pending_batch = len(todo)
