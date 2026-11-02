import { useEffect, useState } from 'react'
import { api, type FeedVideo, type HiddenReason, type LlmUsage } from '../api'
import { VideoRow } from '../components/VideoCard'
import { reasonLabel } from '../utils'

const PAGE = 60
// Matches the API's default view: these are never worth scrolling through.
const NOISE = ['blocked_channel', 'short', 'upcoming', 'live']

export default function Hidden() {
  const [reasons, setReasons] = useState<HiddenReason[]>([])
  const [usage, setUsage] = useState<LlmUsage | null>(null)
  const [reason, setReason] = useState<string | undefined>()
  const [videos, setVideos] = useState<FeedVideo[] | null>(null)
  const [more, setMore] = useState(false)
  // Videos changed on this page, so a row can offer Undo instead of vanishing.
  const [shown, setShown] = useState<Set<string>>(new Set())

  useEffect(() => {
    api.hiddenReasons().then(setReasons).catch(() => {})
    api.llmUsage().then(setUsage).catch(() => {})
  }, [])

  useEffect(() => {
    setVideos(null)
    api.hidden(reason, 0, PAGE).then(vs => { setVideos(vs); setMore(vs.length === PAGE) })
      .catch(() => setVideos([]))
  }, [reason])

  const loadMore = () => api.hidden(reason, videos?.length ?? 0, PAGE)
    .then(vs => { setVideos(v => [...(v ?? []), ...vs]); setMore(vs.length === PAGE) })

  const toggle = (id: string) => {
    const showing = !shown.has(id)
    setShown(s => { const n = new Set(s); if (showing) n.add(id); else n.delete(id); return n })
    api.override(id, showing ? true : null).catch(() =>
      setShown(s => { const n = new Set(s); if (showing) n.delete(id); else n.add(id); return n }))
  }

  const chips = reasons.filter(r => r.reason !== 'blocked_channel')
  const allCount = reasons.filter(r => !NOISE.includes(r.reason)).reduce((n, r) => n + r.count, 0)

  return (
    <div className="mx-auto max-w-3xl pt-2">
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3">
        <h1 className="text-xl font-semibold">Hidden</h1>
        {usage && (
          <p className="text-sm text-muted">
            Classifier: {usd(usage.month_usd)} of {usd(usage.budget_usd)} this month
            {usage.pending > 0 && ` · ${usage.pending} waiting`}
          </p>
        )}
      </div>
      <p className="mb-4 text-sm text-muted">
        What the rules filtered out, and why. Show anyway puts a video in your feed and teaches the classifier.
      </p>

      <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 pb-1 md:mx-0 md:flex-wrap md:px-0">
        <Chip active={!reason} onClick={() => setReason(undefined)}>All · {allCount}</Chip>
        {chips.map(r => (
          <Chip key={r.reason} active={reason === r.reason} onClick={() => setReason(r.reason)}>
            {reasonLabel(r.reason)} · {r.count}
          </Chip>
        ))}
      </div>

      {!videos ? (
        <p className="text-muted">Loading…</p>
      ) : videos.length === 0 ? (
        <p className="rounded-xl bg-surface p-4 text-sm text-muted">Nothing hidden here.</p>
      ) : (
        <div className="space-y-1">
          {videos.map(v => (
            <div key={v.id}>
              <VideoRow v={v} />
              <div className="mb-3 ml-1 flex items-start gap-3 md:ml-[10.5rem]">
                <p className="min-w-0 flex-1 text-xs leading-relaxed text-muted">
                  <span className={shown.has(v.id) ? 'text-fg' : 'rounded bg-surface px-1.5 py-0.5'}>
                    {shown.has(v.id) ? 'Now in your feed' : reasonLabel(v.reason)}
                  </span>
                  {v.one_line && <span> · {v.one_line}</span>}
                </p>
                <button onClick={() => toggle(v.id)}
                  className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium ${shown.has(v.id)
                    ? 'bg-surface text-muted hover:text-fg' : 'bg-fg text-bg'}`}>
                  {shown.has(v.id) ? 'Undo' : 'Show anyway'}
                </button>
              </div>
            </div>
          ))}
          {more && (
            <button onClick={loadMore} className="w-full rounded-xl bg-surface py-2 text-sm hover:bg-surface-hover">
              Load more
            </button>
          )}
        </div>
      )}
    </div>
  )
}

/** Spend is often fractions of a cent, which toFixed(2) would show as $0.00. */
function usd(n: number): string {
  if (n === 0) return '$0'
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium ${active ? 'bg-fg text-bg' : 'bg-surface hover:bg-surface-hover'}`}>
      {children}
    </button>
  )
}
