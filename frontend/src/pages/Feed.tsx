import { useEffect, useState } from 'react'
import type { ContentItem } from '../types'
import { fetchFeed } from '../api'
import VideoCard from '../components/VideoCard'
import PostCard from '../components/PostCard'

type Status = 'loading' | 'error' | 'ready'

export default function Feed() {
  const [items, setItems] = useState<ContentItem[]>([])
  const [status, setStatus] = useState<Status>('loading')
  const [readIds, setReadIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    fetchFeed()
      .then((data) => {
        setItems(data)
        setStatus('ready')
      })
      .catch(() => setStatus('error'))
  }, [])

  const handleRead = (id: string) => {
    setReadIds((prev) => new Set([...prev, id]))
  }

  const visibleItems = items.filter((item) => !readIds.has(item.id))

  if (status === 'loading') {
    return (
      <div className="flex flex-col gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden animate-pulse"
          >
            <div className="w-full aspect-video bg-slate-800" />
            <div className="p-4 space-y-2">
              <div className="h-4 bg-slate-800 rounded w-3/4" />
              <div className="h-3 bg-slate-800 rounded w-1/2" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="text-center py-20 text-slate-500">
        <p className="text-lg font-medium text-slate-400">Unable to load feed</p>
        <p className="text-sm mt-1">Make sure the backend is running.</p>
        <button
          onClick={() => {
            setStatus('loading')
            fetchFeed()
              .then((data) => { setItems(data); setStatus('ready') })
              .catch(() => setStatus('error'))
          }}
          className="mt-4 text-sm text-blue-400 hover:text-blue-300 transition-colors"
        >
          Try again
        </button>
      </div>
    )
  }

  if (visibleItems.length === 0) {
    return (
      <div className="text-center py-24">
        <div className="text-4xl mb-4">✓</div>
        <p className="text-xl font-semibold text-slate-200">You're caught up</p>
        <p className="text-sm text-slate-500 mt-2">
          {items.length === 0
            ? 'No content yet — run the fetch job to populate the feed.'
            : 'All items read. New content fetches twice daily.'}
        </p>
      </div>
    )
  }

  const unreadCount = visibleItems.length

  return (
    <div>
      <p className="text-xs text-slate-600 mb-4">
        {unreadCount} unread item{unreadCount !== 1 ? 's' : ''}
      </p>

      <div className="flex flex-col gap-4">
        {visibleItems.map((item) =>
          item.type === 'video' ? (
            <VideoCard key={item.id} item={item} onRead={handleRead} />
          ) : (
            <PostCard key={item.id} item={item} onRead={handleRead} />
          )
        )}
      </div>

      {unreadCount > 0 && (
        <div className="mt-8 text-center text-xs text-slate-700">
          — {unreadCount} item{unreadCount !== 1 ? 's' : ''} remaining —
        </div>
      )}
    </div>
  )
}
