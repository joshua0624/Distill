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
  feed: () => get<FeedVideo[]>('/api/feed'),
  setTier: async (id: string, tier: Tier, reviewed = true) => {
    const r = await fetch(`/api/channels/${id}/tier`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier, reviewed }),
    })
    if (!r.ok) throw new Error(`setTier: ${r.status}`)
  },
}
