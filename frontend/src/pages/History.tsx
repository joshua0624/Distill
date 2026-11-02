import { useEffect, useState } from 'react'
import { api, type FeedVideo } from '../api'
import { VideoRow } from '../components/VideoCard'

function dayLabel(iso: string): string {
  // last_watched_at comes from SQLite as UTC without a zone marker.
  const d = new Date(iso.replace(' ', 'T') + 'Z')
  const today = new Date()
  const yesterday = new Date(today.getTime() - 86400000)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
}

export default function History() {
  const [videos, setVideos] = useState<FeedVideo[] | null>(null)

  useEffect(() => { api.history().then(setVideos).catch(() => setVideos([])) }, [])

  if (!videos) return <p className="pt-4 text-muted">Loading…</p>

  const groups: [string, FeedVideo[]][] = []
  for (const v of videos) {
    const label = dayLabel(v.last_watched_at!)
    const last = groups[groups.length - 1]
    if (last?.[0] === label) last[1].push(v)
    else groups.push([label, [v]])
  }

  return (
    <div className="mx-auto max-w-3xl pt-2">
      <h1 className="mb-4 text-xl font-semibold">History</h1>
      {videos.length === 0 ? (
        <p className="rounded-xl bg-surface p-4 text-sm text-muted">Videos you watch here show up in this list.</p>
      ) : (
        groups.map(([label, vs]) => (
          <section key={label} className="mb-6">
            <h2 className="mb-2 font-semibold">{label}</h2>
            <div className="space-y-1">
              {vs.map(v => <VideoRow key={v.id} v={v} />)}
            </div>
          </section>
        ))
      )}
    </div>
  )
}
