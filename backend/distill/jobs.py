"""Recurring work: the full update (ingest, discovery, classification) and database backups.
`distill ingest` and `distill backup` run these once; `distill serve --schedule` runs them on
a timer in a background thread, so one always-on process keeps the feed fresh.
"""
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from distill import db
from distill.config import Settings, settings as default_settings

log = logging.getLogger(__name__)

CHECK_EVERY_S = 60


def update(s: Settings = default_settings, *, discover: bool = True, classify: bool = True) -> list[str]:
    """Fetch, discover and classify. Returns summary lines for the CLI or the log."""
    from distill.classify import classify as run_classify
    from distill.ingest import ingest
    from distill.youtube import YouTube

    llm = None
    if classify and os.getenv("ANTHROPIC_API_KEY"):
        import anthropic
        llm = anthropic.Anthropic()
    with db.session() as conn:
        r = ingest(conn, YouTube(), s, discover=discover, llm=llm)
    lines = [f"{r.channels} channels, {r.new_videos} new videos, {r.detailed} detailed, "
             f"{r.short_checks} Shorts checks, {r.visible} visible, {r.errors} errors."]
    if d := r.discovery:
        lines.append(f"Discovery: {d.searches} searches, {d.hn_stories} HN stories, {d.seeds} liked/watched "
                     f"videos mined, {d.llm_channels} suggested channels -> {d.new_videos} new videos "
                     f"from {d.new_channels} new channels, {d.errors} errors.")
    if not classify:
        return lines
    if not llm:
        return lines + ["Skipping classification: no ANTHROPIC_API_KEY in .env."]
    with db.session() as conn:
        c = run_classify(conn, llm, s)
    lines.append(f"Classified {c.classified}, {c.errors} errors, {c.visible} visible in the feed.")
    if c.pending_batch:
        lines.append(f"{c.pending_batch} videos still in a batch; the next run collects them.")
    if c.skipped_budget:
        lines.append(f"{c.skipped_budget} videos skipped: monthly LLM budget reached (llm_monthly_budget_usd).")
    return lines


def backup(dest: Path | None = None, keep: int | None = None, s: Settings = default_settings) -> Path:
    """A consistent copy of the database (safe while the app is writing), keeping the newest
    `keep`. Defaults to a backups folder next to the database (data/backups)."""
    dest = dest or Path(s.db_path).parent / "backups"
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"distill-{datetime.now():%Y-%m-%d-%H%M}.db"
    src = sqlite3.connect(s.db_path)
    try:
        dst = sqlite3.connect(out)
        with dst:
            src.backup(dst)
        dst.close()
    finally:
        src.close()
    keep = keep if keep is not None else s.backup_keep
    for old in sorted(dest.glob("distill-*.db"))[:-keep]:
        old.unlink()
    return out


class Scheduler(threading.Thread):
    """Runs `update` every `ingest_every_h` and `backup` once a day after `backup_hour`.
    Last-run times live in the meta table, so a restart doesn't trigger an immediate rerun."""

    def __init__(self, s: Settings = default_settings):
        super().__init__(daemon=True, name="distill-scheduler")
        self.s = s
        self.stop = threading.Event()

    def run(self) -> None:
        log.info("Scheduler on: update every %sh, backup daily after %02d:00",
                 self.s.ingest_every_h, self.s.backup_hour)
        while not self.stop.wait(CHECK_EVERY_S):
            try:
                self.tick(datetime.now(timezone.utc))
            except Exception:  # keep the thread alive; the next tick tries again
                log.exception("Scheduled job failed")

    def tick(self, now: datetime) -> None:
        if self._due("job:update", timedelta(hours=self.s.ingest_every_h), now):
            self._mark("job:update", now)  # before running, so a crash doesn't loop every minute
            for line in update(self.s):
                log.info("update: %s", line)
        local = now.astimezone()
        today = local.replace(hour=self.s.backup_hour, minute=0, second=0, microsecond=0)
        if local >= today and self._last("job:backup") < today:
            self._mark("job:backup", now)
            log.info("backup: %s", backup(s=self.s))

    def _last(self, key: str) -> datetime:
        with db.session() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return datetime.fromisoformat(row[0]) if row else datetime.min.replace(tzinfo=timezone.utc)

    def _due(self, key: str, every: timedelta, now: datetime) -> bool:
        return self._last(key) <= now - every

    def _mark(self, key: str, now: datetime) -> None:
        with db.session() as conn:
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, now.isoformat()))
