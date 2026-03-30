import { useState } from 'react'
import type { ContentItem } from '../types'
import { markRead } from '../api'
import { formatDuration, formatRelativeDate } from '../utils'

interface Props {
  item: ContentItem
  onRead: (id: string) => void
}

export default function VideoCard({ item, onRead }: Props) {
  const [playing, setPlaying] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  if (dismissed) return null

  const handlePlay = () => setPlaying(true)

  const handleDismiss = async () => {
    setDismissed(true)
    await markRead(item.id).catch(console.error)
    onRead(item.id)
  }

  return (
    <article className="bg-slate-900 rounded-xl overflow-hidden border border-slate-800 hover:border-slate-700 transition-colors">
      {playing ? (
        <div className="relative w-full" style={{ paddingBottom: '56.25%' }}>
          <iframe
            className="absolute inset-0 w-full h-full"
            src={`https://www.youtube-nocookie.com/embed/${item.id}?rel=0&modestbranding=1&autoplay=1`}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
            title={item.title}
          />
        </div>
      ) : (
        <button
          onClick={handlePlay}
          className="relative w-full group cursor-pointer"
          aria-label={`Play ${item.title}`}
        >
          {item.thumbnail_url ? (
            <img
              src={item.thumbnail_url}
              alt=""
              className="w-full aspect-video object-cover"
            />
          ) : (
            <div className="w-full aspect-video bg-slate-800" />
          )}
          <div className="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/40 transition-colors">
            <div className="w-14 h-14 rounded-full bg-white/90 flex items-center justify-center shadow-lg">
              <svg className="w-6 h-6 text-slate-900 ml-1" viewBox="0 0 24 24" fill="currentColor">
                <path d="M8 5v14l11-7z" />
              </svg>
            </div>
          </div>
          {item.duration !== null && (
            <span className="absolute bottom-2 right-2 bg-black/80 text-white text-xs px-1.5 py-0.5 rounded font-mono">
              {formatDuration(item.duration)}
            </span>
          )}
        </button>
      )}

      <div className="p-4">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h2 className="font-medium text-slate-100 leading-snug line-clamp-2">
            {item.title}
          </h2>
          {item.is_low_density === 1 && (
            <span className="shrink-0 text-xs bg-yellow-950 text-yellow-500 border border-yellow-900 rounded px-1.5 py-0.5 font-medium">
              low density
            </span>
          )}
        </div>

        {item.summary ? (
          <p className="text-sm text-slate-400 leading-relaxed mb-3">
            {item.summary}
          </p>
        ) : !item.scored_at ? (
          <p className="text-xs text-slate-600 mb-3 italic">scoring pending…</p>
        ) : null}

        <div className="flex items-center justify-between gap-2 text-xs text-slate-500">
          <span className="flex items-center gap-1.5 min-w-0">
            <span className="shrink-0 bg-red-950 text-red-400 rounded px-1.5 py-0.5 font-medium">
              YT
            </span>
            <span className="truncate">{item.source_name}</span>
          </span>
          <span className="flex items-center gap-2 shrink-0">
            {item.relevance_score !== null && (
              <span className="text-slate-600">{item.relevance_score}%</span>
            )}
            <span>{formatRelativeDate(item.published_at)}</span>
          </span>
        </div>

        <div className="mt-3 flex items-center gap-2">
          {!playing && (
            <button
              onClick={handlePlay}
              className="flex-1 text-sm bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg px-3 py-1.5 transition-colors"
            >
              Watch
            </button>
          )}
          <button
            onClick={handleDismiss}
            className="flex-1 text-sm bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-lg px-3 py-1.5 transition-colors"
          >
            {playing ? 'Done' : 'Skip'}
          </button>
        </div>
      </div>
    </article>
  )
}
