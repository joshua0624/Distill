import { useState } from 'react'
import { api, type FeedVideo } from '../api'

const CLOCK = 'M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z'
const CHECK = 'M5 12.5l4.5 4.5L19 7'

/** Watch Later toggle. `label` shows text next to the icon (watch page); otherwise icon only. */
export default function SaveButton({ v, label, className = '', onChange }: {
  v: FeedVideo
  label?: boolean
  className?: string
  onChange?: (inQueue: boolean) => void
}) {
  const [saved, setSaved] = useState(Boolean(v.in_queue))

  const toggle = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const next = !saved
    setSaved(next)
    onChange?.(next)
    ;(next ? api.addToQueue(v.id) : api.removeFromQueue(v.id)).catch(() => {
      setSaved(!next)
      onChange?.(!next)
    })
  }

  const icon = (
    <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={saved ? CHECK : CLOCK} />
    </svg>
  )

  return label ? (
    <button onClick={toggle}
      className={`flex items-center gap-2 rounded-full bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-hover ${className}`}>
      {icon}
      {saved ? 'Saved' : 'Watch later'}
    </button>
  ) : (
    <button onClick={toggle} title={saved ? 'Remove from Watch later' : 'Watch later'}
      aria-label={saved ? 'Remove from Watch later' : 'Save to Watch later'}
      className={`grid size-8 place-items-center rounded-md bg-black/80 text-white transition-opacity ${className}`}>
      {icon}
    </button>
  )
}
