# Curated Feed — Project Plan

**Personal Content Curation Platform**
*March 2026*

---

## Project Overview

A personal content curation platform that pulls from YouTube and Reddit, filters content through a local LLM, and presents a clean, finite daily feed. No infinite scroll, no algorithmic rabbit holes, no shorts. The platform preserves serendipitous discovery through bounded, intentional mechanisms while reducing total time spent on social media and increasing the quality of time that is spent.

---

## Tech Stack

| Component | Choice | Notes |
|-----------|--------|-------|
| Backend | Python + FastAPI | Lightweight, async-friendly, great Ollama/YouTube library support |
| Frontend | Vite + React + Tailwind + shadcn/ui | Fast dev iteration, polished component library, easy PWA path |
| Database | SQLite | Single-user app, no server to manage, fully portable |
| LLM Runtime | Ollama w/ Llama 3.2 3B | Running 24/7 on Mac Mini; upgrade to Gemma 2 9B Q4 if quality insufficient |
| Hosting | 2018 Mac Mini (i7, 16GB RAM) | Always-on home server for backend, frontend, DB, and LLM |
| Remote Access | Cloudflare Tunnel (free) | Public URL for phone access from anywhere |
| Content Fetch | Cron job, twice daily | YouTube Data API v3 + Reddit API (OAuth, free tier) |
| LLM Batch | Cron job, once daily (~4am) | Scores, summarizes, and flags all unprocessed items |
| Transcripts | youtube-transcript-api | Python library for pulling YouTube video transcripts |
| Dev Environment | MacBook Pro (M4 Max) | Develop locally, deploy to Mac Mini |

---

## Core Design Principles

- **Finite feed**: hard daily cap on items with an explicit empty state when complete
- **No infinite scroll**: content is a bounded set, not a stream
- **No embedded recommendations**: YouTube videos play via embed with no suggested content visible
- **Serendipity by design**: discovery is intentional and bounded, not algorithmic and endless
- **Privacy-first**: all LLM inference runs locally, no data leaves your network
- **Summary-first consumption**: get the insight without watching the full video when possible

---

## Phase 1: Clean Digest MVP

**Goal**: A working web app that displays a daily feed of YouTube videos and Reddit posts from whitelisted sources. Zero recommendation engine, zero shorts, zero infinite scroll.

**Estimated Duration**: 2–3 weeks

### Architecture

- FastAPI backend serving a REST API
- Vite/React frontend consuming the API
- SQLite database with a single `content_items` table; a `type` column distinguishes videos from Reddit posts
- System cron job fetching content twice daily from YouTube and Reddit
- YouTube channel list populated dynamically via OAuth subscription sync; Reddit subreddits defined in config
- Reddit OAuth for API access (free tier, 100 req/min)

### Completion Requirements

| # | Requirement | Priority |
|---|-------------|----------|
| 1 | FastAPI server running and serving content to the React frontend | Must Have |
| 2 | SQLite schema for videos (title, channel, URL, thumbnail, description, duration, fetch date) and Reddit posts (title, subreddit, URL, score, body/preview, fetch date) | Must Have |
| 3 | YouTube Data API v3 integration: OAuth subscription sync pulls the user's subscribed channels dynamically; fetches latest videos from each subscribed channel | Must Have |
| 4 | Reddit API integration pulling top/hot posts from a configurable list of subreddits via OAuth | Must Have |
| 5 | Cron job fetching new content at least twice daily | Must Have |
| 6 | Frontend displays a feed of content cards (thumbnail, title, source, date) showing all unread items; daily item cap deferred to a future phase | Must Have |
| 7 | YouTube videos play via iframe embed within the app — no redirect to YouTube, no suggested videos visible | Must Have |
| 8 | Reddit posts display inline preview with link to full thread | Must Have |
| 9 | No infinite scroll: feed has a definitive end with "You're caught up" empty state | Must Have |
| 10 | YouTube Shorts excluded entirely (filter by duration < 60s or video type) | Must Have |
| 11 | Configuration file (YAML or JSON) for managing whitelisted subreddits; YouTube channels sourced dynamically from OAuth subscription sync | Must Have |
| 12 | API quota usage stays within YouTube free tier (10,000 units/day) using list endpoints over search | Must Have |
| 13 | Error handling and logging for API failures | Should Have |
| 14 | PWA manifest and service worker for mobile home screen install | Should Have |

### Exit Criteria

Phase 1 is complete when the app can be opened on desktop or mobile, displays a finite set of content from chosen channels and subreddits, plays YouTube videos without exposing recommendations or shorts, and shows an explicit end-of-feed state.

---

## Phase 2: Intelligent Filtering & Summaries

**Goal**: Add a local LLM layer that scores every piece of content for relevance, generates summaries, and flags low-density content. The feed becomes actively curated rather than just whitelisted.

**Estimated Duration**: 2–4 weeks
**Depends On**: Phase 1 complete

### Architecture

- Ollama running 24/7 on Mac Mini with Llama 3.2 3B
- Background batch job triggered by cron (~4am daily)
- Single LLM call per item returning: relevance score (0–100), 2–3 sentence summary, and density flag — minimizes round trips on slower hardware
- youtube-transcript-api for pulling video transcripts
- Items are available in the feed immediately after fetch; scores/summaries populate asynchronously as batch completes

### Completion Requirements

| # | Requirement | Priority |
|---|-------------|----------|
| 1 | Ollama installed and running on Mac Mini with Llama 3.2 3B (or upgraded model) | Must Have |
| 2 | YouTube transcript extraction working via youtube-transcript-api for all fetched videos | Must Have |
| 3 | Daily batch job processes each new content item through Ollama | Must Have |
| 4 | Single LLM prompt per item returns: relevance score, summary, and density assessment | Must Have |
| 5 | User interest profile stored as a text file/config that is injected into the scoring prompt | Must Have |
| 6 | Feed sorted by relevance score with a configurable minimum threshold to hide low-relevance items | Must Have |
| 7 | 2–3 sentence summary displayed on each content card | Must Have |
| 8 | Low-density warning badge visible on cards where LLM detects high repetition, excessive sponsors, or low info-to-length ratio | Must Have |
| 9 | Processing is fully asynchronous — frontend never waits on LLM inference | Must Have |
| 10 | Processing status indicator on items that haven't been scored yet | Should Have |
| 11 | Graceful fallback if transcript unavailable: score based on title, description, channel history | Should Have |
| 12 | Processing time per item logged for performance monitoring | Should Have |

### Exit Criteria

Phase 2 is complete when every item in the feed has a relevance score and summary generated by the local LLM, low-quality content is filtered or flagged, and the user can often get the key insight from the summary alone without watching the full video.

---

## Phase 3: Controlled Serendipity

**Goal**: Introduce a bounded discovery mechanism that surfaces content from outside the whitelist, exploring adjacent interests without recreating the infinite rabbit hole.

**Estimated Duration**: 2–3 weeks
**Depends On**: Phase 2 complete

### Architecture

- Discovery engine extracts keywords/topics from highly-rated content over the past 7–30 days
- Uses YouTube search API and Reddit search (budgeted: ~20–30 search queries/day = 2,000–3,000 YouTube units) to find content outside the whitelist
- Dual-mode LLM scoring: relevance mode for whitelist content, quality/substance mode for discovery content
- Engagement with discovery items influences interest graph on a daily cycle, never in real-time

### Completion Requirements

| # | Requirement | Priority |
|---|-------------|----------|
| 1 | Discovery engine extracts topics/keywords from the user's top-rated content over the past 7–30 days | Must Have |
| 2 | System uses extracted keywords to search YouTube and Reddit APIs for content outside the whitelist | Must Have |
| 3 | Discovery items limited to a fixed daily budget (3–5 items) that cannot be expanded | Must Have |
| 4 | Discovery LLM prompt evaluates content quality and substance independent of topical match — filters for well-made, educational, or genuinely interesting content regardless of field | Must Have |
| 5 | Discovery items visually distinct in the feed (labeled "Discover" or similar) | Must Have |
| 6 | Engaging with a discovery item does NOT immediately generate more content from that topic; influence propagates to the next daily cycle at earliest | Must Have |
| 7 | User can dismiss discovery items with a single action | Must Have |
| 8 | Discovery sources one-hop adjacencies from the interest graph (related channels, overlapping subreddit communities) rather than purely random content | Should Have |
| 9 | System tracks which discovery topics have been surfaced to avoid repetitive suggestions | Should Have |
| 10 | User can promote a discovery source to the whitelist directly from the feed card | Should Have |

### Exit Criteria

Phase 3 is complete when the daily feed includes a bounded set of discovery items from outside the whitelist, these items are evaluated on quality rather than just topical match, and engaging with discovery content influences future suggestions gradually rather than triggering an immediate content spiral.

---

## Phase 4: Learning & Personalization

**Goal**: The system learns from explicit user feedback to refine its understanding of what content is worth the user's time, using dynamic prompt engineering rather than ML training pipelines.

**Estimated Duration**: 2–3 weeks
**Depends On**: Phase 3 complete

### Architecture

- Thumbs up/down on content cards plus implicit signals (clicked through vs. skipped, time-to-dismiss)
- Dynamic user interest profile stored as structured text in the database, rebuilt daily from accumulated feedback
- Updated profile injected into LLM prompts for both relevance scoring and discovery sourcing
- No embeddings, no vector DB, no fine-tuning — just evolving text prompts

### Completion Requirements

| # | Requirement | Priority |
|---|-------------|----------|
| 1 | Thumbs up / thumbs down buttons on every content card | Must Have |
| 2 | Feedback stored in the database with content metadata (topic, channel/subreddit, tags) | Must Have |
| 3 | Backend process rebuilds the user interest profile text from accumulated feedback daily | Must Have |
| 4 | Updated profile automatically injected into LLM prompts for scoring and discovery | Must Have |
| 5 | Profile includes both positive interests and explicitly disliked topics/content types | Must Have |
| 6 | User can view and manually edit their interest profile | Must Have |
| 7 | Relevance scores demonstrably shift based on feedback within a few daily cycles | Must Have |
| 8 | Implicit signals tracked: click-through to full content, time-to-dismiss | Should Have |
| 9 | Interest profile change log so user can see how their profile has evolved | Should Have |
| 10 | Guardrail: no single feedback session can dramatically swing the profile; changes smoothed over multiple days | Should Have |

### Exit Criteria

Phase 4 is complete when the user can provide feedback on content, the system visibly adapts its recommendations within a few daily cycles, and the user can inspect and override their auto-generated interest profile.

---

## Phase 5: Mobile, Obsidian Integration & Polish

**Goal**: Make the platform a polished daily driver on both desktop and mobile, with integration into a personal knowledge management workflow.

**Estimated Duration**: 2–4 weeks
**Depends On**: Phase 4 complete (core features stabilized)

### Completion Requirements

| # | Requirement | Priority |
|---|-------------|----------|
| 1 | PWA fully functional: installable on iOS and Android home screens with app-like experience | Must Have |
| 2 | Responsive design: feed, cards, video embeds, and feedback controls all work well on mobile viewports | Must Have |
| 3 | "Send to Vault" button on every content card — exports link, AI summary, and optional user notes as a markdown file to an Obsidian vault directory in iCloud Drive, which syncs to mobile automatically | Must Have |
| 4 | Exported markdown files use a consistent template with YAML frontmatter (source, date, relevance score, tags) | Must Have |
| 5 | "Inbox Zero" screen: when all daily items are viewed/dismissed, display a clear completion message | Must Have |
| 6 | Offline support: previously fetched feed viewable without network connection | Should Have |
| 7 | Daily/weekly usage stats (items consumed, estimated time saved via summaries, discovery items explored) | Should Have |
| 8 | Notification or badge when new daily feed is ready | Should Have |
| 9 | Dark mode | Should Have |
| 10 | Onboarding flow: connect YouTube/Reddit, pick initial channels and subreddits, set daily item cap | Should Have |

### Exit Criteria

Phase 5 is complete when the platform is usable as a daily driver on both phone and desktop, content can be saved to an Obsidian vault with one tap, and the experience feels polished enough to replace YouTube and Reddit browsing habits.

---

## Technical Constraints & Notes

### API Budgets

- **YouTube Data API v3**: 10,000 units/day. Channel/playlist listings = 1 unit. Search = 100 units. Phases 1–2 use list-only fetching. Phase 3 discovery budgets ~20–30 searches/day (2,000–3,000 units), leaving plenty of headroom.
- **Reddit API**: Free tier, 100 requests/minute. Twice-daily fetch across 20–30 subreddits is well within limits.

### LLM Performance (Mac Mini i7, 16GB)

- Llama 3.2 3B: ~4–5GB RAM, ~30–60 seconds per item. Daily batch of 60 items ≈ 30–60 minutes.
- Gemma 2 9B Q4 (upgrade option): ~7–8GB RAM, ~2–3 minutes per item. Daily batch ≈ 2–3 hours.
- Batch runs at ~4am, results ready by morning.

### Data Privacy

- All LLM inference runs locally on the Mac Mini. No content or user data leaves the home network.
- YouTube and Reddit API calls authenticated under your own OAuth credentials.
- SQLite database is local. No cloud sync.

### Development Workflow

- Develop on MacBook Pro (M4 Max), deploy to Mac Mini.
- Mac Mini accessible via Cloudflare Tunnel for remote access from phone or when away from home.

### Secrets Management

API credentials are stored in a `.env` file at the project root and never committed to git. Non-secret config (subreddit lists, interest profile, app settings) lives in `config/`.

```
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN=...   # obtained once via browser OAuth flow, then refreshed automatically
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_REFRESH_TOKEN=...
```

The YouTube OAuth flow (browser-based) is run once on the dev machine to obtain the initial refresh token. Subsequent token refreshes happen automatically.

### Watch History Expansion (Future)

Google Takeout can export your full YouTube watch history as JSON. A separate utility script (outside the main app) will process this export and generate a summary of frequently watched channels not in the current subscription list. This output can be used to manually expand the Reddit/YouTube config. This is not part of any current phase but is planned as a standalone tool.

### Key Dependencies

- Python 3.10+ with FastAPI (raw SQL, no ORM)
- uv (dependency management and virtualenv)
- launchd (macOS process management for FastAPI server)
- Vite + React + Tailwind CSS + shadcn/ui
- Ollama (local LLM runtime)
- youtube-transcript-api (Python)
- SQLite (built into Python)
- Cloudflare Tunnel (free, for remote access)