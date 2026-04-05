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

export async function dismissItem(id: string): Promise<void> {
  const res = await fetch(`/api/items/${encodeURIComponent(id)}/dismiss`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to dismiss item: ${res.status}`)
}

export async function promoteSource(id: string): Promise<void> {
  const res = await fetch(`/api/items/${encodeURIComponent(id)}/promote`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to promote source: ${res.status}`)
}
