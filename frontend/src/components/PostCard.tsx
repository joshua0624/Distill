import type { ContentItem } from '../types'
import { formatRelativeDate } from '../utils'
import Btn from './Btn'

interface Props {
  item: ContentItem
  onDismiss: () => void
  onSave: () => void
  onAddToFeed?: () => void
}

const LinkIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
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

export default function PostCard({ item, onDismiss, onSave, onAddToFeed }: Props) {
  const isDiscovery = item.is_discovery === 1
  const isSaved = item.is_saved === 1

  return (
    <article
      className="rounded-[18px] p-[18px]"
      style={{
        background: 'var(--surface)',
        border: `1px solid ${isDiscovery ? 'var(--badge-discover)' : 'var(--border)'}`,
        boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
      }}
    >
      {/* Meta row */}
      <div className="flex items-center gap-1.5 mb-[6px]" style={{ flexWrap: 'nowrap' }}>
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
          style={{ background: 'var(--badge-reddit)', color: '#fff' }}
        >
          r/
        </span>
        <span className="text-[11px] truncate" style={{ color: 'var(--text-2)' }}>
          {item.source_name}
        </span>
        {item.reddit_score !== null && (
          <span className="text-[11px] flex-shrink-0" style={{ color: 'var(--text-3)' }}>
            · {item.reddit_score.toLocaleString()}
          </span>
        )}
        <span className="text-[11px] ml-auto flex-shrink-0 pl-2" style={{ color: 'var(--text-3)' }}>
          {formatRelativeDate(item.published_at)}
        </span>
      </div>

      {/* Title */}
      <h3
        className="text-sm font-semibold leading-snug line-clamp-3 mb-[5px]"
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
      ) : item.body ? (
        <p
          className="text-[12.5px] leading-[19px] line-clamp-2 mb-3"
          style={{ color: 'var(--text-2)', margin: '0 0 12px' }}
        >
          {item.body}
        </p>
      ) : !item.scored_at ? (
        <p className="text-xs italic mb-3" style={{ color: 'var(--text-3)', margin: '0 0 12px' }}>
          scoring pending…
        </p>
      ) : null}

      {/* Actions */}
      <div className="flex items-center justify-between gap-2.5">
        <div className="flex gap-1.5 flex-wrap">
          <Btn variant="primary" icon={<LinkIcon />} onClick={() => window.open(item.url, '_blank', 'noopener,noreferrer')}>
            Open thread
          </Btn>
          {isDiscovery && onAddToFeed && (
            <Btn variant="discover" icon={<PlusIcon />} onClick={onAddToFeed}>
              Add to feed
            </Btn>
          )}
          <Btn variant={isSaved ? 'saveActive' : 'save'} icon={<BookmarkIcon filled={isSaved} />} onClick={onSave}>
            {isSaved ? 'Saved' : 'Save'}
          </Btn>
          <Btn variant="ghost" onClick={onDismiss}>
            Dismiss
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
    </article>
  )
}
