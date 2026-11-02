# Distill

A personal YouTube front page: trusted channels, filtered mixed channels, no Shorts, no recommendation sidebar. See [docs/v1-spec.md](docs/v1-spec.md).

**Status:** M3 — Takeout import, channel triage, RSS ingest with hard rules, watch page with Watch later queue, resume and history, LLM classification of mixed channels with editable rules and a Hidden view.

## Setup

```bash
uv sync
cd frontend && npm install && npm run build && cd ..
```

Add a YouTube Data API key to `.env` (Google Cloud console → APIs & Services → Credentials → API key, with YouTube Data API v3 enabled):

```
YOUTUBE_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
```

The Anthropic key (console.anthropic.com → API Keys) is for classifying mixed-channel videos with Claude Haiku 5.5. It costs well under $1 a month at normal volume; `llm_monthly_budget_usd` in `config/settings.yaml` caps it.

## Use

1. Export Google Takeout: YouTube only, **history** and **subscriptions**, with history format set to **JSON**. Unzip it.
2. `uv run distill import-takeout ~/Downloads/Takeout`
3. `uv run distill serve` → http://127.0.0.1:8000/triage and sort channels (T / M / B / S, Z to undo; swipe on phones).
4. `uv run distill ingest` to pull new uploads from trusted and mixed channels and classify the mixed ones.

How mixed channels are filtered:
- `config/taste.md` describes what you like; it goes into the classifier's prompt.
- `config/rules.yaml` decides what to show from each classification. After editing it, `uv run distill rules` re-applies it without calling the LLM.
- The **Hidden** page lists what was filtered out and why. **Show anyway** (and **Not interested** on Home) override a decision; overrides become examples in the prompt, and `uv run distill eval` reports how the current rules agree with them.
- `uv run distill classify` classifies on its own (e.g. to collect a batch that was still running); `uv run distill usage` shows spend.

Hard-rule and classifier settings live in `config/settings.yaml`. Frontend dev server with hot reload: `cd frontend && npm run dev` (proxies `/api` to port 8000).

## Notes

- `data/` (database, Takeout) and `.env` are gitignored; this repo is public.
- The venv lives in `.venv.nosync` with `.venv` symlinked to it, so iCloud Desktop sync leaves it alone. iCloud was hiding the venv's `.pth` files, which broke `import distill`.
- Tests: `uv run pytest`
