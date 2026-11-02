# Distill

A personal YouTube front page: trusted channels, filtered mixed channels, no Shorts, no recommendation sidebar. See [docs/v1-spec.md](docs/v1-spec.md).

**Status:** M2 — Takeout import, channel triage, RSS ingest with hard rules, watch page with Watch later queue, resume and history.

## Setup

```bash
uv sync
cd frontend && npm install && npm run build && cd ..
```

Add a YouTube Data API key to `.env` (Google Cloud console → APIs & Services → Credentials → API key, with YouTube Data API v3 enabled):

```
YOUTUBE_API_KEY=...
```

## Use

1. Export Google Takeout: YouTube only, **history** and **subscriptions**, with history format set to **JSON**. Unzip it.
2. `uv run distill import-takeout ~/Downloads/Takeout`
3. `uv run distill serve` → http://127.0.0.1:8000/triage and sort channels (T / M / B / S, Z to undo; swipe on phones).
4. `uv run distill ingest` to pull new uploads from trusted and mixed channels.

Hard-rule settings live in `config/settings.yaml`. Frontend dev server with hot reload: `cd frontend && npm run dev` (proxies `/api` to port 8000).

## Notes

- `data/` (database, Takeout) and `.env` are gitignored; this repo is public.
- The venv lives in `.venv.nosync` with `.venv` symlinked to it, so iCloud Desktop sync leaves it alone. iCloud was hiding the venv's `.pth` files, which broke `import distill`.
- Tests: `uv run pytest`
