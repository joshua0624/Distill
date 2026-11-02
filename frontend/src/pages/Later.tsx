import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type FeedVideo } from '../api'
import { VideoRow } from '../components/VideoCard'
import { duration } from '../utils'

export default function Later() {
  const [queue, setQueue] = useState<FeedVideo[] | null>(null)
  const [dragging, setDragging] = useState<string | null>(null)

  useEffect(() => { api.queue().then(setQueue).catch(() => setQueue([])) }, [])

  const save = (next: FeedVideo[]) => {
    setQueue(next)
    api.reorderQueue(next.map(v => v.id)).catch(() => api.queue().then(setQueue))
  }

  const move = (from: number, to: number) => {
    if (!queue || to < 0 || to >= queue.length || from === to) return
    const next = [...queue]
    const [item] = next.splice(from, 1)
    next.splice(to, 0, item)
    save(next)
  }

  const remove = (id: string) => {
    setQueue(q => q?.filter(v => v.id !== id) ?? null)
    api.removeFromQueue(id).catch(() => api.queue().then(setQueue))
  }

  if (!queue) return <p className="pt-4 text-muted">Loading…</p>

  const total = queue.reduce((s, v) => s + v.duration_s, 0)

  return (
    <div className="mx-auto max-w-3xl pt-2">
      <div className="mb-4 flex items-baseline justify-between gap-3">
        <h1 className="text-xl font-semibold">Watch later</h1>
        {queue.length > 0 && (
          <p className="text-sm text-muted">{queue.length} videos · {duration(total)}</p>
        )}
      </div>

      {queue.length === 0 ? (
        <p className="rounded-xl bg-surface p-4 text-sm text-muted">
          Nothing saved. Use the clock icon on any video in <Link to="/" className="text-fg underline">Home</Link>.
        </p>
      ) : (
        <ol className="space-y-1">
          {queue.map((v, i) => (
            <li key={v.id}
              draggable
              onDragStart={() => setDragging(v.id)}
              onDragEnd={() => setDragging(null)}
              onDragOver={e => {
                e.preventDefault()
                const from = queue.findIndex(q => q.id === dragging)
                if (from !== -1 && from !== i) {
                  const next = [...queue]
                  const [item] = next.splice(from, 1)
                  next.splice(i, 0, item)
                  setQueue(next)
                }
              }}
              onDrop={() => save(queue)}
              className={`flex items-center gap-1 rounded-xl ${dragging === v.id ? 'opacity-50' : ''}`}>
              <span className="hidden w-6 shrink-0 cursor-grab text-center text-sm text-muted md:block" aria-hidden>⋮⋮</span>
              <div className="min-w-0 flex-1">
                <VideoRow v={v}>
                  <div className="flex shrink-0 flex-col items-center justify-center gap-0.5 text-muted">
                    <IconButton label="Move up" disabled={i === 0} onClick={() => move(i, i - 1)} d="M6 15l6-6 6 6" />
                    <IconButton label="Remove" onClick={() => remove(v.id)} d="M6 6l12 12M18 6L6 18" />
                    <IconButton label="Move down" disabled={i === queue.length - 1} onClick={() => move(i, i + 1)} d="M6 9l6 6 6-6" />
                  </div>
                </VideoRow>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function IconButton({ label, d, onClick, disabled }: {
  label: string
  d: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button onClick={onClick} disabled={disabled} aria-label={label} title={label}
      className="grid size-8 place-items-center rounded-full hover:bg-surface hover:text-fg disabled:opacity-30">
      <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>
    </button>
  )
}
