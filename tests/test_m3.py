import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from distill import classify as cl
from distill import db
from distill.api import app
from distill.config import Settings, settings
from distill.rules import decide_llm, load_llm_rules

CH = "UC" + "m" * 22
GOOD = {"category": "gaming", "topic": "VCT final", "format": "highlights", "clickbait": False,
        "substance": "high", "slop_signals": [], "interest_match": "strong", "one_line": "VCT final highlights"}


@pytest.mark.parametrize("change, visible, reason", [
    ({}, True, "rule:Matches my interests"),
    ({"format": "reaction"}, False, "rule:Reaction or compilation"),
    ({"slop_signals": ["reupload"]}, False, "rule:Slop"),
    # Title style alone never hides a video.
    ({"clickbait": True, "substance": "low"}, True, "rule:Matches my interests"),
    ({"slop_signals": ["rage_bait", "misleading_title"]}, True, "rule:Matches my interests"),
    ({"interest_match": "none"}, False, "rule:Not my interests"),
])
def test_shipped_rules(change, visible, reason):
    d = decide_llm({**GOOD, **change}, load_llm_rules())
    assert (d.visible, d.reason) == (visible, reason)


def test_rule_conditions(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("- name: Deep\n  show_if: { substance_at_least: medium, category: [learning, tech_ai] }\n"
                    "- default: hide\n")
    rules = load_llm_rules(path)
    assert decide_llm({**GOOD, "category": "learning", "substance": "high"}, rules).reason == "rule:Deep"
    assert not decide_llm({**GOOD, "category": "learning", "substance": "low"}, rules).visible
    assert decide_llm({**GOOD, "category": "gaming"}, rules).reason == "rule:rule 2"


def _usage(**kw):
    return NS(input_tokens=600, output_tokens=120, cache_read_input_tokens=1000,
              cache_creation_input_tokens=0, **kw)


def _message(data=GOOD, stop="end_turn"):
    return NS(stop_reason=stop, usage=_usage(), content=[NS(type="text", text=json.dumps(data))])


class FakeClient:
    """Answers per title: titles containing 'react' come back as reactions, 'refuse' as a refusal."""
    def __init__(self, batch_status="ended"):
        self.calls, self.batch_requests, self.batch_status = [], [], batch_status
        self.messages = NS(create=self._create, batches=NS(
            create=self._batch_create, retrieve=lambda bid: NS(processing_status=self.batch_status),
            results=self._results))

    def _answer(self, params):
        text = params["messages"][0]["content"]
        if "refuse" in text:
            return _message(stop="refusal")
        return _message({**GOOD, "format": "reaction"} if "react" in text else GOOD)

    def _create(self, **params):
        self.calls.append(params)
        return self._answer(params)

    def _batch_create(self, requests):
        self.batch_requests = requests
        return NS(id="msgbatch_1")

    def _results(self, bid):
        return [NS(custom_id=r["custom_id"], result=NS(type="succeeded", message=self._answer(r["params"])))
                for r in self.batch_requests]


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "t.db"))
    c = db.connect()
    c.execute("INSERT INTO channels (id, title, source, tier, reviewed) VALUES (?, 'Mixed', 'x', 'mixed', 1)", (CH,))
    for i, title in enumerate(["Grand final recap", "I react to the final", "please refuse", "Rank 1 guide"]):
        c.execute("INSERT INTO videos (id, channel_id, title, description, published_at, duration_s, "
                  "is_short, details_at, source) VALUES (?, ?, ?, 'd', ?, 900, 0, datetime('now'), 'rss')",
                  (f"vid0000000{i}", CH, title, f"2026-11-0{i + 1}T00:00:00Z"))
    from distill.ingest import apply_rules
    apply_rules(c)
    yield c
    c.close()


def reasons(conn):
    return dict(conn.execute("SELECT video_id, reason FROM decisions ORDER BY video_id").fetchall())


def test_classify_direct(conn):
    fake = FakeClient()
    r = cl.classify(conn, fake, Settings(llm_batch_threshold=20))
    assert (r.classified, r.errors, r.visible) == (3, 1, 2)
    assert reasons(conn) == {"vid00000000": "rule:Matches my interests", "vid00000001": "rule:Reaction or compilation",
                             "vid00000002": "llm_error", "vid00000003": "rule:Matches my interests"}
    p = fake.calls[0]
    assert p["model"] == "claude-haiku-5-5" and p["thinking"] == {"type": "disabled"}
    assert p["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "Houston Rockets" in p["system"][0]["text"]
    usage = conn.execute("SELECT requests, cost_usd FROM llm_usage").fetchone()
    assert usage["requests"] == 4 and usage["cost_usd"] == pytest.approx(4 * (600 * 0.1 + 120 * 0.5 + 1000 * 0.01) / 1e6)
    # Nothing left to do: a second run makes no calls, and errors aren't retried.
    assert cl.classify(conn, fake, Settings()).classified == 0 and len(fake.calls) == 4
    # A new prompt version reclassifies everything the rules decided, errors included.
    conn.execute("UPDATE classifications SET prompt_version = 'old'")
    assert len(cl.pending_videos(conn)) == 4


def test_classify_batch(conn):
    fake = FakeClient(batch_status="in_progress")
    r = cl.classify(conn, fake, Settings(llm_batch_threshold=2), wait_s=0)
    assert r.submitted_batch == "msgbatch_1" and r.pending_batch == 4 and not fake.calls
    assert cl.pending_videos(conn) == []  # in flight, so not resubmitted
    fake.batch_status = "ended"
    r = cl.classify(conn, fake, Settings(llm_batch_threshold=2))
    assert (r.collected, r.classified, r.visible) == (1, 3, 2)
    cost = conn.execute("SELECT cost_usd FROM llm_usage").fetchone()[0]
    assert cost == pytest.approx(4 * (600 * 0.1 + 120 * 0.5 + 1000 * 0.01) / 1e6 / 2)


def test_budget_ceiling(conn):
    conn.execute("INSERT INTO llm_usage (date, cost_usd) VALUES (date('now'), 2.999)")
    fake = FakeClient()
    r = cl.classify(conn, fake, Settings(llm_monthly_budget_usd=3.0))
    assert r.classified == 1 and r.skipped_budget == 3 and len(fake.calls) == 1


def test_override_and_eval(conn):
    cl.classify(conn, FakeClient(), Settings())
    client = TestClient(app)
    assert {v["id"] for v in client.get("/api/hidden").json()} == {"vid00000001", "vid00000002"}
    r = client.post("/api/videos/vid00000001/override", json={"visible": True}).json()
    assert r == {"visible": 1, "reason": "override", "overridden": 1}
    client.post("/api/videos/vid00000000/override", json={"visible": False})
    feed = [v["id"] for v in client.get("/api/feed").json()]
    assert feed == ["vid00000003", "vid00000001"]
    # Overrides become labels: both disagree with what the rules did.
    e = cl.evaluate(conn)
    assert e["agree"] == 0 and len(e["wrongly_hidden"]) == 1 and len(e["wrongly_shown"]) == 1
    assert "not wanted" in cl.system_prompt(conn)
    # Clearing hands the video back to the rules.
    r = client.post("/api/videos/vid00000001/override", json={"visible": None}).json()
    assert r == {"visible": 0, "reason": "rule:Reaction or compilation", "overridden": 0}
    usage = client.get("/api/llm/usage").json()
    assert usage["pending"] == 0 and usage["month_usd"] > 0
