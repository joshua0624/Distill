import type { ReactNode } from 'react'
import type { ContentItem } from '../types'
import VideoCard from '../components/VideoCard'
import PostCard from '../components/PostCard'

type Tab = 'feed' | 'discover' | 'saved'

interface FeedViewProps {
  tab: Tab
  feedItems: ContentItem[]
  discoverItems: ContentItem[]
  savedItems: ContentItem[]
  onDismissFeed: (id: string) => void
  onDismissDiscover: (id: string) => void
  onAddToFeed: (id: string) => void
  onToggleSave: (item: ContentItem) => void
  onRemoveSaved: (id: string) => void
}

// ─── Section divider ───
function TierDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <span
        className="text-[11px] font-bold tracking-[0.07em] uppercase whitespace-nowrap"
        style={{ color: 'var(--tier-label)' }}
      >
        {label}
      </span>
      <div className="flex-1 h-px" style={{ background: 'var(--border)' }} />
    </div>
  )
}

// ─── Empty state ───
function EmptyState({ icon, title, subtitle }: { icon: ReactNode; title: string; subtitle: string }) {
  return (
    <div className="text-center py-20 px-5">
      <div
        className="w-14 h-14 rounded-full flex items-center justify-center mx-auto mb-5"
        style={{ background: 'var(--surface-3)', color: 'var(--accent)' }}
      >
        {icon}
      </div>
      <h2 className="text-[19px] font-semibold mb-2" style={{ color: 'var(--text)' }}>
        {title}
      </h2>
      <p className="text-[13px] leading-[21px]" style={{ color: 'var(--text-3)' }}>
        {subtitle}
      </p>
    </div>
  )
}

// ─── Card renderer ───
function Card({
  item,
  onDismiss,
  onSave,
  onAddToFeed,
}: {
  item: ContentItem
  onDismiss: () => void
  onSave: () => void
  onAddToFeed?: () => void
}) {
  return item.type === 'video' ? (
    <VideoCard item={item} onDismiss={onDismiss} onSave={onSave} onAddToFeed={onAddToFeed} />
  ) : (
    <PostCard item={item} onDismiss={onDismiss} onSave={onSave} onAddToFeed={onAddToFeed} />
  )
}

// ─── Tiered list (Top Picks ≥90, Everything Else <90) ───
function TieredList({
  items,
  onDismiss,
  onSave,
  onAddToFeed,
}: {
  items: ContentItem[]
  onDismiss: (id: string) => void
  onSave: (item: ContentItem) => void
  onAddToFeed?: (id: string) => void
}) {
  const top = items.filter((i) => i.relevance_score !== null && i.relevance_score >= 90)
  const rest = items.filter((i) => i.relevance_score === null || i.relevance_score < 90)

  return (
    <>
      {top.length > 0 && (
        <div className={rest.length > 0 ? 'mb-8' : ''}>
          <TierDivider label="Top picks" />
          <div className="flex flex-col gap-3.5">
            {top.map((item) => (
              <Card
                key={item.id}
                item={item}
                onDismiss={() => onDismiss(item.id)}
                onSave={() => onSave(item)}
                onAddToFeed={onAddToFeed ? () => onAddToFeed(item.id) : undefined}
              />
            ))}
          </div>
        </div>
      )}
      {rest.length > 0 && (
        <>
          <TierDivider label={top.length > 0 ? 'Everything else' : `${rest.length} items`} />
          <div className="flex flex-col gap-3.5">
            {rest.map((item) => (
              <Card
                key={item.id}
                item={item}
                onDismiss={() => onDismiss(item.id)}
                onSave={() => onSave(item)}
                onAddToFeed={onAddToFeed ? () => onAddToFeed(item.id) : undefined}
              />
            ))}
          </div>
        </>
      )}
    </>
  )
}

// ─── Icons for empty states ───
const CheckIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="20 6 9 17 4 12" />
  </svg>
)
const CompassIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <circle cx="12" cy="12" r="10" />
    <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
  </svg>
)
const ClockIcon = () => (
  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
    <circle cx="12" cy="12" r="10" />
    <polyline points="12 6 12 12 16 14" />
  </svg>
)

// ─── Main export ───
export default function FeedView({
  tab,
  feedItems,
  discoverItems,
  savedItems,
  onDismissFeed,
  onDismissDiscover,
  onAddToFeed,
  onToggleSave,
  onRemoveSaved,
}: FeedViewProps) {
  if (tab === 'feed') {
    if (feedItems.length === 0) {
      return (
        <EmptyState
          icon={<CheckIcon />}
          title="You're caught up"
          subtitle="New content is fetched twice daily."
        />
      )
    }
    return (
      <TieredList
        items={feedItems}
        onDismiss={onDismissFeed}
        onSave={onToggleSave}
      />
    )
  }

  if (tab === 'discover') {
    if (discoverItems.length === 0) {
      return (
        <EmptyState
          icon={<CompassIcon />}
          title="No discoveries right now"
          subtitle="The LLM will surface new content outside your subscriptions soon."
        />
      )
    }
    return (
      <>
        <p className="text-xs mb-[22px] leading-[18px]" style={{ color: 'var(--text-3)' }}>
          Content surfaced by the LLM from outside your subscriptions.
        </p>
        <TieredList
          items={discoverItems}
          onDismiss={onDismissDiscover}
          onSave={onToggleSave}
          onAddToFeed={onAddToFeed}
        />
      </>
    )
  }

  // saved tab
  if (savedItems.length === 0) {
    return (
      <EmptyState
        icon={<ClockIcon />}
        title="Nothing saved yet"
        subtitle="Bookmark items from your feed or discoveries to save them here."
      />
    )
  }
  return (
    <>
      <p className="text-xs mb-[22px] font-medium" style={{ color: 'var(--text-3)' }}>
        {savedItems.length} saved {savedItems.length === 1 ? 'item' : 'items'}
      </p>
      <div className="flex flex-col gap-3.5">
        {savedItems.map((item) => (
          <Card
            key={item.id}
            item={item}
            onDismiss={() => onRemoveSaved(item.id)}
            onSave={() => onToggleSave(item)}
          />
        ))}
      </div>
    </>
  )
}
