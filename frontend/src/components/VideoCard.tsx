import { useState } from 'react'
import type { ContentItem } from '../types'
import { formatDuration, formatRelativeDate } from '../utils'
import Btn from './Btn'

interface Props {
  item: ContentItem
  onDismiss: () => void
  onSave: () => void
  onAddToFeed?: () => void
}

const PlayIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
    <polygon points="5 3 19 12 5 21 5 3" />
  </svg>
)

const PlusIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 5v14M5 12h14" />
  </svg>
)

const BookmarkIcon = ({ filled }: { filled: boolean }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2">
    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  </svg>
)

export default function VideoCard({ item, onDismiss, onSave, onAddToFeed }: Props) {
  const [playing, setPlaying] = useState(false)
  const isDiscovery = item.is_discovery === 1
  const isSaved = item.is_saved === 1

  return (
    <article
      className="rounded-[18px] overflow-hidden"
      style={{
        background: 'var(--surface)',
        border: `1px solid ${isDiscovery ? 'var(--badge-discover)' : 'var(--border)'}`,
        boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
      }}
    >
      {/* Full-width embed when playing */}
      {playing && (
        <div className="relative w-full" style={{ paddingBottom: '56.25%' }}>
          <iframe
            className="absolute inset-0 w-full h-full"
            src={`https://www.youtube-nocookie.com/embed/${item.id}?rel=0&modestbranding=1&autoplay=1`}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            title={item.title}
          />
        </div>
      )}

      <div className="flex gap-4 p-[18px]">
        {/* Side thumbnail — hidden while playing */}
        {!playing && (
          <button
            onClick={() => setPlaying(true)}
            className="relative flex-shrink-0 rounded-xl overflow-hidden cursor-pointer group"
            style={{ width: 120, height: 78, background: 'var(--surface-2)', border: 'none', padding: 0 }}
            aria-label={`Play ${item.title}`}
          >
            {item.thumbnail_url ? (
              <img src={item.thumbnail_url} alt="" className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full" style={{ background: 'var(--surface-2)' }} />
            )}
            {item.duration !== null && (
              <span
                className="absolute bottom-1 right-1 text-white text-[10px] font-semibold px-1.5 py-px rounded"
                style={{ background: 'rgba(0,0,0,0.72)', fontVariantNumeric: 'tabular-nums' }}
              >
                {formatDuration(item.duration)}
              </span>
            )}
            <div className="absolute inset-0 flex items-center justify-center bg-black/15 opacity-0 group-hover:opacity-100 transition-opacity">
              <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.9)' }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="#1a1a1a"><polygon points="6 3 20 12 6 21 6 3" /></svg>
              </div>
            </div>
          </button>
        )}

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Meta row */}
          <div className="flex items-center gap-1.5 mb-[5px]" style={{ flexWrap: 'nowrap' }}>
            {isDiscovery && item.discovery_topic && (
              <span
                className="text-[10px] font-bold px-[7px] py-px rounded-md leading-4 whitespace-nowrap flex-shrink-0"
                style={{
                  color: 'var(--badge-discover)',
                  background: 'color-mix(in srgb, var(--badge-discover) 10%, transparent)',
                }}
              >
                {item.discovery_topic}
              </span>
            )}
            <span
              className="inline-flex items-center px-2 py-px rounded-md text-[11px] font-semibold leading-[18px] flex-shrink-0"
              style={{ background: 'var(--badge-yt)', color: '#fff' }}
            >
              YT
            </span>
            <span className="text-[11px] truncate" style={{ color: 'var(--text-2)' }}>
              {item.source_name}
            </span>
            <span className="text-[11px] ml-auto flex-shrink-0 pl-2" style={{ color: 'var(--text-3)' }}>
              {formatRelativeDate(item.published_at)}
            </span>
          </div>

          {/* Title */}
          <h3
            className="text-sm font-semibold leading-snug line-clamp-2 mb-[5px]"
            style={{ color: 'var(--text)', margin: 0, marginBottom: 5 }}
          >
            {item.title}
          </h3>

          {/* Summary */}
          {item.summary ? (
            <p
              className="text-[12.5px] leading-[19px] line-clamp-2 mb-3"
              style={{ color: 'var(--text-2)', margin: '0 0 12px' }}
            >
              {item.summary}
            </p>
          ) : !item.scored_at ? (
            <p className="text-xs italic mb-3" style={{ color: 'var(--text-3)', margin: '0 0 12px' }}>
              scoring pending…
            </p>
          ) : null}

          {/* Actions */}
          <div className="flex items-center justify-between gap-2.5">
            <div className="flex gap-1.5 flex-wrap">
              <Btn variant="primary" icon={<PlayIcon />} onClick={() => setPlaying(true)}>
                {playing ? 'Playing' : 'Watch'}
              </Btn>
              {isDiscovery && onAddToFeed && (
                <Btn variant="discover" icon={<PlusIcon />} onClick={onAddToFeed}>
                  Add to feed
                </Btn>
              )}
              <Btn variant={isSaved ? 'saveActive' : 'save'} icon={<BookmarkIcon filled={isSaved} />} onClick={onSave}>
                {isSaved ? 'Saved' : 'Later'}
              </Btn>
              <Btn variant="ghost" onClick={onDismiss}>
                {playing ? 'Done' : 'Skip'}
              </Btn>
            </div>
            {item.relevance_score !== null && (
              <span
                className="text-xs font-bold flex-shrink-0"
                style={{ color: 'var(--accent)', fontVariantNumeric: 'tabular-nums' }}
              >
                {item.relevance_score}%
              </span>
            )}
          </div>
        </div>
      </div>
    </article>
  )
}
