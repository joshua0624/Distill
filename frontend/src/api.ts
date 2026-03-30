import type { ContentItem } from './types'

export async function fetchFeed(): Promise<ContentItem[]> {
  const res = await fetch('/api/feed')
  if (!res.ok) throw new Error(`Failed to fetch feed: ${res.status}`)
  return res.json()
}

export async function markRead(id: string): Promise<void> {
  const res = await fetch(`/api/items/${encodeURIComponent(id)}/read`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to mark read: ${res.status}`)
}
