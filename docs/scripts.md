# Scripts Reference

All Python commands should be run from the project root (`/home/joshua/Distill`). Frontend commands should be run from the `frontend/` directory.

---

## Setup & First Run Order

Run these in order when setting up the project for the first time:

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `uv run python -m backend.models.init_db` | Create the SQLite database schema |
| 2 | `uv run python scripts/get_youtube_token.py` | Get YouTube OAuth token (opens browser) |
| 3 | Copy token to `.env` as `YOUTUBE_REFRESH_TOKEN=...` | Store credentials |
| 4 | `uv run python scripts/sync_youtube.py` | Sync YouTube subscriptions into DB |
| 5 | `uv run uvicorn backend.main:app --reload` | Start the backend API server (port 8000) |
| 6 | `npm run dev` (in `frontend/`) | Start the frontend dev server (port 5173) |
| 7 | `uv run python -m backend.jobs.fetch` | Fetch initial content from YouTube & Reddit |
| 8 | `uv run python -m backend.jobs.score` | Score and summarize content via Ollama |

---

## Setup Scripts

### `scripts/get_youtube_token.py`
One-time OAuth flow to get a YouTube refresh token. Opens a browser for the Google consent screen and prints the token to stdout.

```bash
uv run python scripts/get_youtube_token.py
```

### `scripts/sync_youtube.py`
Syncs YouTube subscriptions from the authenticated account into the `channels` table. Run once on setup and whenever subscriptions change.

```bash
uv run python scripts/sync_youtube.py
```

---

## Database Scripts

### `backend/models/init_db.py`
Creates the SQLite database schema: `channels`, `content_items`, and `discovery_topics` tables, plus indexes. Safe to run only once — run before the server starts for the first time.

```bash
uv run python -m backend.models.init_db
```

### `backend/models/migrate_phase2.py`
Phase 2 migration — adds `scored_at` and `transcript` columns to `content_items`. Safe to run multiple times.

```bash
uv run python -m backend.models.migrate_phase2
```

### `backend/models/migrate.py`
Phase 3 migration — adds `is_discovery` and `discovery_topic` columns to `content_items`, and creates the `discovery_topics` tracking table.

```bash
uv run python -m backend.models.migrate
```

---

## Batch Jobs

These run on a schedule via launchd (plists live in `~/Library/LaunchAgents/` on macOS) but can also be triggered manually.

### `backend/jobs/fetch.py`
Fetches new content from all YouTube subscriptions (up to 10 videos/channel) and Reddit subreddits (25 posts/subreddit). Runs twice daily.

```bash
uv run python -m backend.jobs.fetch
```

### `backend/jobs/score.py`
Processes all unscored items: fetches transcripts for videos, then sends each item to Ollama for scoring. Writes `relevance_score` (0–100), `summary`, `is_low_density`, and `transcript` back to the DB. Runs nightly at 4am.

```bash
uv run python -m backend.jobs.score
```

### `backend/jobs/discover.py`
Runs discovery: surfaces content from outside the subscription whitelist using topic-based search, up to the configured `discovery_daily_cap`. Items appear in feed with a "Discover" badge.

```bash
uv run python -m backend.jobs.discover
```

---

## Utility Scripts

### `scripts/clear_scores.py`
Resets all scoring fields (`relevance_score`, `summary`, `is_low_density`, `scored_at`, `transcript`) on every item so the score job reprocesses them. Useful for testing or after changing the scoring prompt.

```bash
uv run python scripts/clear_scores.py
```

---

## Backend Server

### `backend/main.py`
FastAPI application. Serves the REST API on port 8000. CORS is configured for localhost:5173 (Vite dev) and localhost:4173 (Vite preview).

```bash
# Development (auto-reload on file changes)
uv run uvicorn backend.main:app --reload

# Production
uv run uvicorn backend.main:app
```

---

## Frontend (`frontend/`)

```bash
npm run dev       # Dev server on port 5173 (hot reload)
npm run build     # Production build
npm run preview   # Preview production build on port 4173
npm run lint      # Run ESLint
```

---

## Daily Operation (Steady State)

Once set up, the jobs run automatically. To trigger manually:

```bash
uv run python -m backend.jobs.fetch    # Pull new content
uv run python -m backend.jobs.score    # Score unscored items
uv run python -m backend.jobs.discover # Run discovery
```
