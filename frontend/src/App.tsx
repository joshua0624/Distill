import { useState, useEffect, useCallback } from 'react'
import type { ContentItem } from './types'
import {
  fetchFeed,
  fetchSaved,
  markRead,
  dismissItem,
  promoteSource,
  saveItem,
  unsaveItem,
} from './api'
import FeedView from './pages/Feed'

type Tab = 'feed' | 'discover' | 'saved'
type Theme = 'light' | 'dark'

// ─── Icons ───
const SunIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="5" />
    <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
  </svg>
)
const MoonIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
)
const InboxIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
    <path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
  </svg>
)
const CompassIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <circle cx="12" cy="12" r="10" />
    <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
  </svg>
)
const BookmarkIcon = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  </svg>
)

// ─── Tab bar ───
function TabBar({
  active,
  onChange,
  counts,
}: {
  active: Tab
  onChange: (t: Tab) => void
  counts: { feed: number; discover: number; saved: number }
}) {
  const tabs: { id: Tab; label: string; icon: React.ReactNode; count: number }[] = [
    { id: 'feed', label: 'Feed', icon: <InboxIcon />, count: counts.feed },
    { id: 'discover', label: 'Discover', icon: <CompassIcon />, count: counts.discover },
    { id: 'saved', label: 'Watch Later', icon: <BookmarkIcon />, count: counts.saved },
  ]

  return (
    <nav className="flex gap-0.5 px-1">
      {tabs.map((t) => {
        const on = active === t.id
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className="flex items-center gap-1.5 px-3.5 rounded-[10px] text-[13px] cursor-pointer transition-all whitespace-nowrap"
            style={{
              paddingTop: 7,
              paddingBottom: 7,
              background: on ? 'var(--accent-soft)' : 'transparent',
              color: on ? 'var(--accent)' : 'var(--tab-inactive)',
              fontWeight: on ? 600 : 500,
              border: 'none',
              fontFamily: 'inherit',
              lineHeight: '20px',
            }}
          >
            <span style={{ display: 'flex', opacity: on ? 1 : 0.7 }}>{t.icon}</span>
            {t.label}
            {t.count > 0 && (
              <span
                className="text-[11px] font-bold leading-[18px] px-1.5 rounded-[10px]"
                style={{
                  fontVariantNumeric: 'tabular-nums',
                  background: on ? 'var(--accent)' : 'var(--surface-3)',
                  color: on ? '#fff' : 'var(--text-3)',
                }}
              >
                {t.count}
              </span>
            )}
          </button>
        )
      })}
    </nav>
  )
}

// ─── Loading skeleton ───
function LoadingSkeleton() {
  return (
    <div className="flex flex-col gap-3.5">
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="rounded-[18px] p-[18px] flex gap-4 animate-pulse"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
        >
          <div className="flex-shrink-0 rounded-xl" style={{ width: 120, height: 78, background: 'var(--surface-3)' }} />
          <div className="flex-1 space-y-2">
            <div className="h-3 rounded" style={{ background: 'var(--surface-3)', width: '40%' }} />
            <div className="h-4 rounded" style={{ background: 'var(--surface-3)', width: '85%' }} />
            <div className="h-3 rounded" style={{ background: 'var(--surface-3)', width: '70%' }} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Error state ───
function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="text-center py-20">
      <p className="text-[15px] font-medium mb-1" style={{ color: 'var(--text)' }}>
        Unable to load feed
      </p>
      <p className="text-sm mb-4" style={{ color: 'var(--text-3)' }}>
        Make sure the backend is running.
      </p>
      <button
        onClick={onRetry}
        className="text-sm transition-opacity hover:opacity-75"
        style={{ color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
      >
        Try again
      </button>
    </div>
  )
}

// ─── App ───
export default function App() {
  const [theme, setTheme] = useState<Theme>('light')
  const [tab, setTab] = useState<Tab>('feed')
  const [feedItems, setFeedItems] = useState<ContentItem[]>([])
  const [savedItems, setSavedItems] = useState<ContentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  // Detect system preference on mount
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    setTheme(mq.matches ? 'dark' : 'light')
    const h = (e: MediaQueryListEvent) => setTheme(e.matches ? 'dark' : 'light')
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [])

  // Apply .dark class to <html>
  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  // ─── Data loading ───
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const [feed, saved] = await Promise.all([fetchFeed(), fetchSaved()])
      setFeedItems(feed)
      setSavedItems(saved)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // ─── Actions ───
  const handleDismissFeed = useCallback((id: string) => {
    setFeedItems((p) => p.filter((i) => i.id !== id))
    markRead(id).catch(console.error)
  }, [])

  const handleDismissDiscover = useCallback((id: string) => {
    setFeedItems((p) => p.filter((i) => i.id !== id))
    dismissItem(id).catch(console.error)
  }, [])

  const handleAddToFeed = useCallback((id: string) => {
    setFeedItems((p) => p.filter((i) => i.id !== id))
    promoteSource(id).catch(console.error)
  }, [])

  const handleToggleSave = useCallback((item: ContentItem) => {
    if (item.is_saved === 1) {
      // unsave
      setFeedItems((p) => p.map((i) => (i.id === item.id ? { ...i, is_saved: 0 } : i)))
      setSavedItems((p) => p.filter((i) => i.id !== item.id))
      unsaveItem(item.id).catch(console.error)
    } else {
      // save
      const updated = { ...item, is_saved: 1 }
      setFeedItems((p) => p.map((i) => (i.id === item.id ? updated : i)))
      setSavedItems((p) => {
        // avoid duplicates if item was already in saved list somehow
        const filtered = p.filter((i) => i.id !== item.id)
        return [...filtered, updated]
      })
      saveItem(item.id).catch(console.error)
    }
  }, [])

  const handleRemoveSaved = useCallback((id: string) => {
    setSavedItems((p) => p.filter((i) => i.id !== id))
    setFeedItems((p) => p.map((i) => (i.id === id ? { ...i, is_saved: 0 } : i)))
    unsaveItem(id).catch(console.error)
  }, [])

  // ─── Derived data ───
  const regularItems = feedItems.filter((i) => i.is_discovery === 0)
  const discoverItems = feedItems.filter((i) => i.is_discovery === 1)

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)' }}>
      {/* Sticky header */}
      <header
        className="sticky top-0 z-50"
        style={{
          background: 'var(--header-bg)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div className="max-w-[660px] mx-auto px-6">
          <div className="flex items-center justify-between" style={{ height: 52 }}>
            <h1
              style={{
                margin: 0,
                fontSize: 24,
                fontWeight: 400,
                fontFamily: "'Instrument Serif', serif",
                letterSpacing: '-0.01em',
                color: 'var(--text)',
              }}
            >
              Distill
            </h1>
            <button
              onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
              className="w-8 h-8 flex items-center justify-center rounded-lg transition-colors hover:opacity-75"
              style={{
                background: 'none',
                border: '1px solid var(--border)',
                color: 'var(--text-3)',
                cursor: 'pointer',
              }}
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
            </button>
          </div>
          <div className="pb-2.5" style={{ marginBottom: -1 }}>
            <TabBar
              active={tab}
              onChange={setTab}
              counts={{
                feed: regularItems.length,
                discover: discoverItems.length,
                saved: savedItems.length,
              }}
            />
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-[660px] mx-auto px-6 py-7 pb-20">
        {loading ? (
          <LoadingSkeleton />
        ) : error ? (
          <ErrorState onRetry={loadData} />
        ) : (
          <FeedView
            tab={tab}
            feedItems={regularItems}
            discoverItems={discoverItems}
            savedItems={savedItems}
            onDismissFeed={handleDismissFeed}
            onDismissDiscover={handleDismissDiscover}
            onAddToFeed={handleAddToFeed}
            onToggleSave={handleToggleSave}
            onRemoveSaved={handleRemoveSaved}
          />
        )}
      </main>
    </div>
  )
}
