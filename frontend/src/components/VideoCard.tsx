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

const HOVER = 'opacity-100 md:opacity-0 md:group-hover:opacity-100'

/** Grid card, like YouTube's home page. `onHide` adds a "Not interested" button. */
export default function VideoCard({ v, onQueueChange, onHide, note }: {
  v: FeedVideo
  onQueueChange?: (inQueue: boolean) => void
  onHide?: () => void
  /** Extra line under the stats, e.g. where a discovered video came from. */
  note?: string
}) {
  return (
    <div className="group relative">
      <Link to={`/watch/${v.id}`} title={v.one_line ?? undefined}>
        <Thumb v={v} />
      </Link>
      <div className={`absolute right-1.5 top-1.5 flex flex-col gap-1 ${HOVER}`}>
        <SaveButton v={v} onChange={onQueueChange} />
        {onHide && (
          <button onClick={onHide} title="Not interested" aria-label="Not interested: hide this video"
            className="grid size-8 place-items-center rounded-md bg-black/80 text-white">
            <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        )}
      </div>
      <div className="mt-3 flex gap-3">
        <ChannelAvatar v={v} />
        <Link to={`/watch/${v.id}`} className="min-w-0" title={v.one_line ?? undefined}>
          <h3 className="line-clamp-2 font-medium leading-snug">{v.title}</h3>
          <p className="mt-1 text-sm text-muted">{v.channel_title}</p>
          <p className="text-sm text-muted">
            {v.views != null && `${compact(v.views)} views · `}{timeAgo(v.published_at)}
          </p>
          {note && <p className="mt-0.5 line-clamp-1 text-xs text-muted">{note}</p>}
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
