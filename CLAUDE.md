# Distill

Personal content curation platform. Pulls from YouTube & Reddit, scores/summarizes via local LLM, serves a finite daily feed. No infinite scroll, no shorts, no recommendations.

## Stack
- **Backend**: Python 3.10+, FastAPI, SQLite (raw SQL — no ORM)
- **Frontend**: Vite + React + Tailwind + shadcn/ui
- **LLM**: Ollama (Llama 3.2 3B) on Mac Mini i7 16GB — batch processing, not real-time
- **APIs**: YouTube Data API v3 (OAuth for subscription sync, budget 10k units/day — use list endpoints not search), Reddit API (OAuth, free tier)
- **Hosting**: Mac Mini (always-on), Cloudflare Tunnel for remote access
- **Transcripts**: youtube-transcript-api
- **Dependency management**: uv
- **Process management**: launchd (macOS-native, plist in `~/Library/LaunchAgents/`)

## Architecture
- YouTube channel list pulled dynamically via OAuth subscription sync; Reddit subreddits defined in `config/`
- System cron fetches content 2x/day, stores in SQLite single `content_items` table (`type` column distinguishes video vs. post)
- Daily 4am batch: Ollama scores relevance, generates summary, flags low-density — single LLM call per item
- Frontend consumes REST API, never waits on LLM — items appear unscored until batch completes
- Feed shows all unread items with hard end state: "You're caught up"

## Key Constraints
- YouTube embeds only (no redirects, no suggested videos)
- Shorts filtered out (duration < 60s) — requires separate `videos.list` call for `contentDetails`
- Discovery engagement influences next-day feed, never real-time
- All LLM inference local — no data leaves the network
- Obsidian "Send to Vault" writes markdown to an iCloud Drive vault folder (syncs to mobile automatically)

## Secrets Management
Credentials live in a `.env` file at project root — never committed to git.
```
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN=...
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_REFRESH_TOKEN=...
```
Non-secret app config (subreddit whitelist, interest profile, app settings) lives in `config/`.

## Project Structure
```
distill/
├── backend/          # FastAPI app
│   ├── api/          # Route handlers
│   ├── services/     # YouTube, Reddit, Ollama integrations
│   ├── models/       # SQLite models
│   └── jobs/         # Cron/batch jobs
├── frontend/         # Vite + React app
│   ├── components/   # UI components
│   └── pages/        # Feed, settings, profile
└── config/           # Reddit subreddits whitelist, interest profile, app settings
```# Distill
