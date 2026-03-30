import { useState } from 'react'
import type { ContentItem } from '../types'
import { markRead } from '../api'
import { formatRelativeDate } from '../utils'

interface Props {
  item: ContentItem
  onRead: (id: string) => void
}

export default function PostCard({ item, onRead }: Props) {
  const [dismissed, setDismissed] = useState(false)

  if (dismissed) return null

  const handleDismiss = async () => {
    setDismissed(true)
    await markRead(item.id).catch(console.error)
    onRead(item.id)
  }

  const score =
    item.reddit_score !== null
      ? item.reddit_score >= 1000
        ? `${(item.reddit_score / 1000).toFixed(1)}k`
        : String(item.reddit_score)
      : null

  return (
    <article className="bg-slate-900 rounded-xl border border-slate-800 hover:border-slate-700 transition-colors p-4">
      <div className="flex gap-3">
        {item.thumbnail_url && (
          <img
            src={item.thumbnail_url}
            alt=""
            className="w-16 h-16 rounded-lg object-cover shrink-0 self-start"
          />
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-start gap-2">
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-slate-100 leading-snug hover:text-blue-400 transition-colors line-clamp-3"
            >
              {item.title}
            </a>
            {item.is_low_density === 1 && (
              <span className="shrink-0 text-xs bg-yellow-950 text-yellow-500 border border-yellow-900 rounded px-1.5 py-0.5 font-medium">
                low density
              </span>
            )}
          </div>

          {item.summary ? (
            <p className="mt-1.5 text-sm text-slate-400 leading-relaxed line-clamp-2">
              {item.summary}
            </p>
          ) : item.body ? (
            <p className="mt-1.5 text-sm text-slate-400 leading-relaxed line-clamp-2">
              {item.body}
            </p>
          ) : !item.scored_at ? (
            <p className="mt-1.5 text-xs text-slate-600 italic">scoring pending…</p>
          ) : null}
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-2 text-xs text-slate-500">
        <span className="flex items-center gap-2 min-w-0">
          <span className="shrink-0 bg-orange-950 text-orange-400 rounded px-1.5 py-0.5 font-medium">
            r/
          </span>
          <span className="truncate">{item.source_name}</span>
          {score !== null && (
            <span className="shrink-0 text-slate-500">↑{score}</span>
          )}
        </span>
        <span className="flex items-center gap-2 shrink-0">
          {item.relevance_score !== null && (
            <span className="text-slate-600">{item.relevance_score}%</span>
          )}
          <span>{formatRelativeDate(item.published_at)}</span>
        </span>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 text-center text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg px-3 py-1.5 transition-colors"
        >
          Open thread
        </a>
        <button
          onClick={handleDismiss}
          className="flex-1 text-sm bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-lg px-3 py-1.5 transition-colors"
        >
          Dismiss
        </button>
      </div>
    </article>
  )
}
