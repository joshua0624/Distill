import { Link } from 'react-router-dom'
import type { FeedVideo } from '../api'
import { compact, duration, timeAgo } from '../utils'
import SaveButton from './SaveButton'

export function Thumb({ v, className = '' }: { v: FeedVideo; className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-xl bg-surface ${className}`}>
      <img src={v.thumb_url ?? `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`} alt=""
        loading="lazy" className="aspect-video w-full object-cover" />
      <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1 text-xs font-medium text-white">
        {duration(v.duration_s)}
      </span>
      {v.watched_pct != null && v.watched_pct > 0 && (
        <div className="absolute inset-x-0 bottom-0 h-1 bg-white/30">
          <div className="h-full bg-accent" style={{ width: `${Math.max(v.watched_pct, 3)}%` }} />
        </div>
      )}
    </div>
  )
}

export function ChannelAvatar({ v, size = 'size-9' }: { v: FeedVideo; size?: string }) {
  return v.channel_thumb ? (
    <img src={v.channel_thumb} alt="" className={`${size} shrink-0 rounded-full bg-surface`} />
  ) : (
    <div className={`grid ${size} shrink-0 place-items-center rounded-full bg-surface text-sm text-muted`}>
      {v.channel_title.slice(0, 1)}
    </div>
  )
}

/** Grid card, like YouTube's home page. */
export default function VideoCard({ v, onQueueChange }: {
  v: FeedVideo
  onQueueChange?: (inQueue: boolean) => void
}) {
  return (
    <div className="group relative">
      <Link to={`/watch/${v.id}`}>
        <Thumb v={v} />
      </Link>
      <SaveButton v={v} onChange={onQueueChange}
        className="absolute right-1.5 top-1.5 opacity-100 md:opacity-0 md:group-hover:opacity-100" />
      <div className="mt-3 flex gap-3">
        <ChannelAvatar v={v} />
        <Link to={`/watch/${v.id}`} className="min-w-0">
          <h3 className="line-clamp-2 font-medium leading-snug">{v.title}</h3>
          <p className="mt-1 text-sm text-muted">{v.channel_title}</p>
          <p className="text-sm text-muted">
            {v.views != null && `${compact(v.views)} views · `}{timeAgo(v.published_at)}
          </p>
        </Link>
      </div>
    </div>
  )
}

/** Compact row: small thumbnail on the left. Used in the watch-page sidebar, queue and history. */
export function VideoRow({ v, active, children }: {
  v: FeedVideo
  active?: boolean
  children?: React.ReactNode
}) {
  return (
    <div className={`flex gap-2 rounded-xl p-1 ${active ? 'bg-surface' : ''}`}>
      <Link to={`/watch/${v.id}`} className="w-40 shrink-0">
        <Thumb v={v} className="rounded-lg" />
      </Link>
      <Link to={`/watch/${v.id}`} className="min-w-0 flex-1 py-0.5">
        <h3 className="line-clamp-2 text-sm font-medium leading-snug">{v.title}</h3>
        <p className="mt-1 truncate text-xs text-muted">{v.channel_title}</p>
        <p className="text-xs text-muted">{timeAgo(v.published_at)}</p>
      </Link>
      {children}
    </div>
  )
}
