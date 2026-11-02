# Distill — V1 Spec

*November 2026 · personal project, single user*

## 1. What this is

A personal replacement for the YouTube home page. It shows videos from channels I trust, filters videos from channels that are hit-or-miss, and adds a capped amount of discovery. No Shorts, no slop, no recommendation sidebar. Playback still uses YouTube's embedded player, so YouTube Premium (ad-free) carries over.

It's not meant to be purely intellectual. Tech talks and podcasts sit alongside Rockets/Dolphins highlights and VALORANT/Rocket League content. The goal is **less garbage**, not "only educational content".

### Lessons from the first attempt (March 2026)
| Problem | V1 response |
|---|---|
| A 3B local model gave inconsistent quality judgments | A small cloud model (Haiku-class), run in batches |
| One 0–100 score against a paragraph of interests couldn't be debugged | The LLM extracts **structured fields**; **rules** decide what to show |
| Every video went through the LLM, including ones from trusted channels | **Lanes**: trusted channels skip the LLM entirely |
| Transcript fetches got rate-limited, so the filter fell back to title-only | Transcripts aren't needed; metadata is enough for most videos |
| Building a clean subscription list by hand was too hard | Channel list **built from Takeout watch history**, then quick triage |

### Goals
- Feed quality I trust without second-guessing it.
- Feels like YouTube on desktop, and works well as a PWA on my phone.
- Easy upkeep: the channel list maintains itself through feedback.
- LLM cost of cents per day, with a hard ceiling well under $5/day.

### Non-goals (V1)
- Background or lock-screen audio (V2).
- Reddit or any non-video source (V2).
- Feed caps or stopping points (V2; the feed can be long for now).
- Multiple users, accounts, or a public deployment.

---

## 2. Architecture

```
            ┌──────────────── Mac Mini (always on) ────────────────┐
 YouTube RSS ─┐                                                    │
 YouTube API ─┼─> ingest jobs ─> SQLite <─ FastAPI <─ Cloudflare ──┼─> Browser / PWA
 HN Algolia ──┘        │            ▲                   Tunnel +   │
                       └> classify ─┘                   Access     │
                          (Claude Batch API)                       │
            └──────────────────────────────────────────────────────┘
```

| Component | Choice |
|---|---|
| Backend | Python, FastAPI |
| DB | SQLite (one file, easy to back up) |
| Jobs | APScheduler in-process or cron; ingest every ~2h, classify after each ingest |
| LLM | Anthropic API, `claude-haiku-5-5`, Message Batches API + prompt caching; model name in config |
| Frontend | Vite + React + TypeScript + Tailwind, `vite-plugin-pwa` |
| Hosting | 2018 Mac Mini (no local LLM needed anymore) |
| Remote access | Cloudflare Tunnel, protected by **Cloudflare Access** (email one-time code), so the app isn't open to the internet |

---

## 3. Data sources

### 3.1 Google Takeout (one-time setup, can be re-imported)
- `watch-history.json` (**JSON format**, not the default HTML). Each entry has a video title/URL, channel name/URL, and timestamp. Drop entries marked as ads (`details` → "From Google Ads").
- `subscriptions.csv`: channel ID, URL, title.
- Stored in `data/takeout/`, which is **gitignored**. The repo is public.

### 3.2 New uploads from channels
- RSS: `https://www.youtube.com/feeds/videos.xml?channel_id=<id>`. Free, no quota, returns the latest 15 uploads.
- Fill in details with `videos.list` (`contentDetails,statistics,snippet`): 1 quota unit per 50 videos. Gives duration, view/like counts, full description, tags, and whether it's a live broadcast.

### 3.3 Discovery (see §6)
- YouTube `search.list` (100 units per call).
- HN Algolia API (free) for upvoted youtube.com links.
- Recent uploads from channels near ones I like.

### 3.4 Quota budget (10,000 units/day)
| Use | Units/day (est.) |
|---|---|
| `videos.list` details (~1,000 videos) | ~20 |
| `channels.list` for triage/discovery | ~20 |
| Standing discovery searches (≤ 40) | ≤ 4,000 |
| Headroom | ~5,900 |

---

## 4. Channels and lanes

Each channel has one **tier**:

| Tier | Meaning | Filtering |
|---|---|---|
| `trusted` | Always want to see this | Hard rules only (§5.1). No LLM. |
| `mixed` | Sometimes good, sometimes not | Hard rules + LLM classification + rules |
| `blocked` | Never show | Dropped at ingest |
| `candidate` | Found through discovery or Takeout, not reviewed | Same as `mixed`, but shown in the Discovery lane with a daily cap |

**Sports rules** are a special case of trusted: a channel plus a title pattern, e.g. `channel=NBA AND title~"Rockets" AND title~"Full Game Highlights"`. These let me follow the official league channels without getting all of their output.

### 4.1 Triage (first-run setup)
1. Import Takeout and group watch history by channel: `watch_count`, `last_watched`, `watches_last_180d`, `is_subscribed`.
2. Rank by a simple score (recent watches weighted higher, plus a bonus for subscribed channels).
3. **Triage screen**: one card per channel showing avatar, name, watch count, last watched, and its 5 latest titles. Actions: **Trusted / Mixed / Block / Skip**, with keyboard shortcuts on desktop and swipe on mobile.
4. Channels never reviewed start as `candidate`. The top ~150 should take about 10 minutes.
5. The triage screen stays available later for reviewing new candidates.

### 4.2 Self-maintenance
- **Promotion suggestion**: a `candidate`/`mixed` channel with ≥ 3 thumbs-up (or ≥ 3 videos watched past 50%) in 60 days → "Promote to Trusted?"
- **Demotion suggestion**: a `trusted` channel with ≥ 2 thumbs-down, or 10+ videos shown and none opened in 60 days → "Move to Mixed?"
- Suggestions appear as a small badge on the Channels page. Nothing changes without my confirmation.

---

## 5. Filtering pipeline

```
ingest -> hard rules -> (trusted? show) -> LLM classify -> rules -> show / hide (with reason)
```

### 5.1 Hard rules (every video, no LLM)
- **Shorts**: duration ≤ 180s, **or** `GET youtube.com/shorts/<id>` answers 200 without redirecting (regular videos redirect to `/watch`). Checked only when duration ≤ 180s.
- Minimum length: configurable, default 4 min (sports highlights can use a lower per-rule minimum).
- Scheduled premieres and upcoming live streams are held back until they're available.
- Blocked channels and blocked title keywords (config).

### 5.2 LLM classification (mixed and candidate lanes)
Input: title, channel name, description (first ~1,500 chars), duration, tags, published date, view/like counts, channel tier, plus a cached block with my taste notes and ~20 recent labeled examples (§7).

Output (JSON, enforced with structured output):
```json
{
  "category": "tech_ai | sports | gaming | talks_podcasts | learning | fitness | other",
  "topic": "short free text, e.g. 'Claude Code workflows'",
  "format": "full_game | highlights | analysis | reaction | podcast | interview | talk | tutorial | course | documentary | news | vlog | compilation | commentary | other",
  "clickbait": true,
  "substance": "low | medium | high",
  "slop_signals": ["ai_voiceover", "reupload", "listicle", "rage_bait", "..."],
  "interest_match": "strong | some | none",
  "one_line": "what the video actually is, in plain words"
}
```

### 5.3 Rules (`config/rules.yaml`, editable)
```yaml
- hide_if: { format: [reaction, compilation] }
- hide_if: { slop_signals_any: [ai_voiceover, reupload] }
- hide_if: { clickbait: true, substance: low }
- hide_if: { interest_match: none }
- show_if: { category: sports, format: [full_game, highlights, analysis] }
- default: show_if_interest_match_at_least: some
```
- Every hidden video stores the **rule that hid it**. A "Hidden" view lists them with reasons, and I can override from there. Overrides become training examples.
- Each classification stores `model` and `prompt_version`, so videos can be re-classified when the prompt changes.

### 5.4 Cost control
- Batch API (results usually back within minutes to hours, which is fine) and caching of the fixed prompt part.
- Expected ~200–400 classifications/day at ~700 tokens each, which is cents per day.
- Daily token ceiling in config. When it's reached, skip classification and leave videos pending; never fall back to showing them unfiltered.

---

## 6. Discovery

All discovered videos come from `candidate` channels and get the strict filter, plus:
- **Daily cap** on discovery videos shown (default 10), displayed as their own row/chip.
- **Sources**:
  1. **Adjacent channels**: when I thumbs-up or watch more than 50% of a video, fetch recent uploads from channels it links to or mentions in the description (podcast guests, collaborators) and from its featured channels (`channelSections`).
  2. **Standing searches**: `config/discovery.yaml` holds queries per interest (e.g. "Houston Rockets", "Claude Code", "VALORANT VOD review", "home lab"). Ordered by date, `videoDuration=medium|long`, run 1–3× daily within the quota budget.
  3. **Hacker News**: Algolia search for `youtube.com` stories above a points threshold, last 7 days.
  4. **LLM channel ideas** (weekly): ask for channels that match my profile, **check each one with `channels.list`**, and add verified ones as candidates.
- A channel stays `candidate` until I triage it or it gets auto-suggested for promotion.

---

## 7. Feedback loop

| Signal | Source |
|---|---|
| 👍 / 👎 | Buttons on cards and on the watch page |
| Hide ("not interested") | Card menu |
| Watched % | IFrame API progress, sampled every 15s |
| Override | "Show anyway" / "Hide this" from the Hidden view or feed |

Uses:
- **Few-shot examples**: the prompt's cached block includes ~20 recent labeled examples (balanced positive/negative, mixed categories), refreshed daily.
- **Takeout as cold start**: videos watched more than once, or from heavily watched channels, are early positive examples.
- **Channel promotion/demotion** suggestions (§4.2).
- **Evaluation**: a small "hand-labeled set" (≈100 videos) and a script that reports how well the rules + classifier agree with my labels. Run it whenever the prompt or rules change.

---

## 8. Frontend

Keep YouTube's layout; remove YouTube's hooks.

### Pages
- **Home**: responsive thumbnail grid with category chips (All · Tech/AI · Sports · Gaming · Talks & Podcasts · Learning · Discovery). Cards show thumbnail, duration, title, channel, age, and the LLM's `one_line` as a hover/long-press tooltip. Newest first within lanes; trusted channels slightly favored.
- **Watch**: embedded player (IFrame API) on the left. The right column shows **my Watch Later queue**, never recommendations. 👍/👎, "open on YouTube", and channel tier controls sit under the player. On `ENDED`, show my own end screen (next in queue, or "done").
- **Watch Later**: ordered queue, drag to reorder.
- **History**: what I've watched, with resume position.
- **Channels**: all channels by tier, triage mode, and promotion/demotion suggestions.
- **Hidden**: filtered-out videos with the rule that hid each one; override actions.

### Player
- Use a regular `youtube.com/embed` (not `youtube-nocookie`) so a signed-in Premium session can apply. **Verify with Premium on desktop and iOS Safari/PWA before relying on it.**
- `rel=0`, `modestbranding=1`, `playsinline=1`; resume from saved position.

### PWA / mobile
- Installable, standalone display, dark theme by default.
- Mobile layout: single-column cards, bottom tab bar (Home / Later / Channels), swipe gestures in triage.
- Offline: app shell cached; feed needs a network connection.

---

## 9. Data model (SQLite)

```
channels      (id PK, title, handle, thumb_url, tier, source, watch_count, last_watched_at,
               is_subscribed, added_at, tier_changed_at)
sport_rules   (id, channel_id, title_pattern, min_duration_s, enabled)
videos        (id PK, channel_id, title, description, published_at, duration_s, is_short,
               is_live, views, likes, tags_json, lane, source, discovered_via, fetched_at)
classifications (video_id PK, category, topic, format, clickbait, substance,
               slop_signals_json, interest_match, one_line, model, prompt_version, created_at)
decisions     (video_id PK, visible, rule_id, overridden, decided_at)
feedback      (id, video_id, signal, value, created_at)        -- up/down/hide/override
progress      (video_id PK, position_s, watched_pct, last_watched_at)
queue         (video_id PK, position, added_at)
discovery_queries (id, query, category, enabled, last_run_at)
takeout_history (video_id, channel_id, watched_at)              -- raw import
llm_usage     (date PK, input_tokens, output_tokens, batches)
```

---

## 10. Privacy and repo hygiene
- Public repo: `.env`, `data/` (Takeout, SQLite DB) and any exports are **gitignored before the first commit**.
- Only video metadata (title, description, channel) goes to the LLM API, never watch history in bulk. Few-shot examples contain titles and my labels only.
- Cloudflare Access in front of the tunnel; the FastAPI app also checks the Access JWT.

---

## 11. Milestones

| # | Milestone | Done when |
|---|---|---|
| M1 | **Ingest + triage** | Takeout imported; triage screen works; RSS + `videos.list` ingest for trusted/mixed channels; hard rules (Shorts, length) applied |
| M2 | **Feed + player** | YouTube-style home grid and watch page with queue sidebar; progress/resume; Watch Later; trusted lane fully usable |
| M3 | **Classification** | Batch classification for mixed lane; rules.yaml; Hidden view with reasons; overrides; usage ceiling; eval script on labeled set |
| M4 | **Discovery + feedback** | Discovery lane with cap; standing searches, adjacent channels, HN; 👍/👎; few-shot refresh; promotion/demotion suggestions |
| M5 | **Deploy + PWA** | Running on Mac Mini behind Tunnel + Access; installable on phone; Premium playback verified |

M1 + M2 alone should be useful as a cleaner subscription feed.

---

## 12. V2 backlog
- Background/lock-screen audio: yt-dlp audio extraction to a private podcast RSS feed.
- Reddit and other non-video sources.
- Feed bounding: daily caps, "you're caught up", session timers.
- Spoiler-free sports mode (hide scores/titles/thumbnails until tapped).
- Transcripts for borderline classifications only (throttled, cached).
- Embedding-based similarity to past likes as an extra ranking signal.

## 13. Open questions
- Reuse parts of the March 2026 codebase (in git history) or start clean? Ingest/UI scaffolding may be reusable; scoring is replaced entirely.
- Does Premium carry into iframe embeds in an installed iOS PWA? (Test in M5.)
- Default minimum duration: 4 min overall, lower for sports highlights?
- Final category list for chips.
