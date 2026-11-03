from datetime import datetime, timedelta, timezone

import pytest

from distill import db, jobs
from distill.config import Settings, settings


@pytest.fixture
def s(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))
    with db.session() as conn:
        conn.execute("INSERT INTO channels (id, title, source) VALUES ('UCx', 'X', 'x')")
    return Settings(db_path=str(tmp_path / "t.db"), ingest_every_h=2, backup_hour=4, backup_keep=2)


def test_backup_copies_and_prunes(s, tmp_path):
    dest = tmp_path / "backups"
    for name in ["distill-2026-01-01-0400.db", "distill-2026-01-02-0400.db"]:
        (dest / name).parent.mkdir(exist_ok=True)
        (dest / name).write_bytes(b"old")
    out = jobs.backup(dest, s=s)
    with db.session(out) as conn:
        assert conn.execute("SELECT title FROM channels").fetchone()[0] == "X"
    assert sorted(p.name for p in dest.iterdir()) == ["distill-2026-01-02-0400.db", out.name]


def test_scheduler(s, tmp_path, monkeypatch):
    runs = []
    monkeypatch.setattr(jobs, "update", lambda s: runs.append("update") or ["ok"])
    monkeypatch.setattr(jobs, "backup", lambda s: runs.append("backup") or tmp_path / "b.db")
    sched = jobs.Scheduler(s)
    morning = datetime.now().astimezone().replace(hour=5, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    sched.tick(morning)
    assert runs == ["update", "backup"]
    sched.tick(morning + timedelta(minutes=30))  # nothing due yet
    assert runs == ["update", "backup"]
    sched.tick(morning + timedelta(hours=2, minutes=1))  # next update; backup already done today
    assert runs == ["update", "backup", "update"]
    sched.tick(morning + timedelta(days=1))  # a new day: both again
    assert runs == ["update", "backup", "update", "update", "backup"]
