export type Tier = 'trusted' | 'mixed' | 'blocked' | 'candidate'

export interface Channel {
  id: string
  title: string
  handle: string | null
  thumb_url: string | null
  tier: Tier
  reviewed: number
  is_subscribed: number
  watch_count: number
  watches_180d: number
  last_watched_at: string | null
  rank: number
}

export interface TriageChannel extends Channel {
  watched_titles: string[]
}

export interface Upload {
  id: string
  title: string
  published_at: string
  thumb_url: string | null
}

export interface Preview {
  thumb_url: string | null
  latest: Upload[]
  shorts_share: number
}

export interface TriageStats {
  reviewed: Partial<Record<Tier, number>>
  unreviewed: number
}

export interface FeedVideo {
  id: string
  title: string
  published_at: string
  duration_s: number
  views: number | null
  thumb_url: string | null
  channel_id: string
  channel_title: string
  channel_thumb: string | null
  position_s: number | null
  watched_pct: number | null
  last_watched_at: string | null
  in_queue: number
}

export interface VideoDetail extends FeedVideo {
  description: string | null
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json()
}

export const api = {
  triageStats: () => get<TriageStats>('/api/triage/stats'),
  triageNext: (limit = 20) => get<TriageChannel[]>(`/api/triage/next?limit=${limit}`),
  preview: (id: string) => get<Preview>(`/api/channels/${id}/preview`),
  channels: (tier?: Tier) => get<Channel[]>(`/api/channels${tier ? `?tier=${tier}` : ''}`),
  feed: (offset = 0, limit = 48) => get<FeedVideo[]>(`/api/feed?limit=${limit}&offset=${offset}`),
  video: (id: string) => get<VideoDetail>(`/api/videos/${id}`),
  history: () => get<FeedVideo[]>('/api/history'),
  queue: () => get<FeedVideo[]>('/api/queue'),
  addToQueue: (id: string) => send('POST', `/api/queue/${id}`),
  removeFromQueue: (id: string) => send('DELETE', `/api/queue/${id}`),
  reorderQueue: (ids: string[]) => send('PUT', '/api/queue', { ids }),
  saveProgress: (id: string, position_s: number, duration_s: number) =>
    send('PUT', `/api/progress/${id}`, { position_s, duration_s }),
  /** Fire-and-forget save that survives the page closing. */
  saveProgressOnExit: (id: string, position_s: number, duration_s: number) =>
    fetch(`/api/progress/${id}`, {
      method: 'PUT',
      keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ position_s, duration_s }),
    }),
  setTier: (id: string, tier: Tier, reviewed = true) =>
    send('POST', `/api/channels/${id}/tier`, { tier, reviewed }),
}

async function send(method: string, path: string, body?: unknown): Promise<void> {
  const r = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${method} ${path}: ${r.status}`)
}
