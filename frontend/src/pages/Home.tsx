import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type FeedVideo } from '../api'
import { compact, duration, timeAgo } from '../utils'

export default function Home() {
  const [videos, setVideos] = useState<FeedVideo[] | null>(null)

  useEffect(() => { api.feed().then(setVideos).catch(() => setVideos([])) }, [])

  if (!videos) return <p className="pt-4 text-muted">Loading…</p>
  if (videos.length === 0) {
    return (
      <div className="mx-auto mt-10 max-w-md text-center text-sm text-muted">
        <p className="mb-2 text-base text-fg">Nothing in your feed yet.</p>
        <p>
          <Link to="/triage" className="text-fg underline">Triage some channels</Link>, then run{' '}
          <code className="rounded bg-surface px-1.5 py-0.5">uv run distill ingest</code>.
        </p>
      </div>
    )
  }

  return (
    <div className="grid gap-x-4 gap-y-8 pt-2 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
      {videos.map(v => (
        // Bare embed until the M2 watch page exists: no recommendations, no sidebar.
        <a key={v.id} href={`https://www.youtube.com/embed/${v.id}?autoplay=1&rel=0`} target="_blank" rel="noreferrer">
          <div className="relative">
            <img src={v.thumb_url ?? `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`} alt=""
              loading="lazy" className="aspect-video w-full rounded-xl bg-surface object-cover" />
            <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1 text-xs font-medium text-white">
              {duration(v.duration_s)}
            </span>
          </div>
          <div className="mt-3 flex gap-3">
            {v.channel_thumb ? (
              <img src={v.channel_thumb} alt="" className="size-9 shrink-0 rounded-full bg-surface" />
            ) : (
              <div className="grid size-9 shrink-0 place-items-center rounded-full bg-surface text-sm text-muted">
                {v.channel_title.slice(0, 1)}
              </div>
            )}
            <div className="min-w-0">
              <h3 className="line-clamp-2 font-medium leading-snug">{v.title}</h3>
              <p className="mt-1 text-sm text-muted">{v.channel_title}</p>
              <p className="text-sm text-muted">
                {v.views != null && `${compact(v.views)} views · `}{timeAgo(v.published_at)}
              </p>
            </div>
          </div>
        </a>
      ))}
    </div>
  )
}
