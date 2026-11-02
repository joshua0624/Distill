import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Preview, type Tier, type TriageChannel, type TriageStats } from '../api'
import { timeAgo } from '../utils'

type Choice = Exclude<Tier, 'candidate'> | 'skip'

const CHOICES: { choice: Choice; label: string; key: string; hint: string; cls: string }[] = [
  { choice: 'blocked', label: 'Block', key: 'b', hint: '← swipe', cls: 'text-blocked' },
  { choice: 'skip', label: 'Skip', key: 's', hint: 'tap', cls: 'text-muted' },
  { choice: 'mixed', label: 'Mixed', key: 'm', hint: '↑ swipe', cls: 'text-mixed' },
  { choice: 'trusted', label: 'Trusted', key: 't', hint: 'swipe →', cls: 'text-trusted' },
]

const KEYS: Record<string, Choice> = {
  t: 'trusted', ArrowRight: 'trusted',
  m: 'mixed', ArrowUp: 'mixed',
  b: 'blocked', ArrowLeft: 'blocked',
  s: 'skip', ' ': 'skip',
}

export default function Triage() {
  const [queue, setQueue] = useState<TriageChannel[]>([])
  const [previews, setPreviews] = useState<Record<string, Preview>>({})
  const [stats, setStats] = useState<TriageStats | null>(null)
  const [history, setHistory] = useState<TriageChannel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const loadingMore = useRef(false)
  const requested = useRef(new Set<string>())

  const refill = useCallback(async () => {
    if (loadingMore.current) return
    loadingMore.current = true
    try {
      const [next, s] = await Promise.all([api.triageNext(30), api.triageStats()])
      setStats(s)
      setQueue(q => {
        const seen = new Set(q.map(c => c.id))
        return [...q, ...next.filter(c => !seen.has(c.id))]
      })
    } catch (e) {
      setError(String(e))
    } finally {
      loadingMore.current = false
      setLoading(false)
    }
  }, [])

  useEffect(() => { refill() }, [refill])

  // Prefetch previews for the current card and the next two.
  useEffect(() => {
    for (const c of queue.slice(0, 3)) {
      if (requested.current.has(c.id)) continue
      requested.current.add(c.id)
      api.preview(c.id)
        .then(p => setPreviews(prev => ({ ...prev, [c.id]: p })))
        .catch(() => setPreviews(prev => ({ ...prev, [c.id]: { thumb_url: null, latest: [], shorts_share: 0 } })))
    }
    if (!loading && queue.length < 8) refill()
  }, [queue, loading, refill])

  const current = queue[0]

  const decide = useCallback((choice: Choice) => {
    if (!current) return
    const tier: Tier = choice === 'skip' ? 'candidate' : choice
    setQueue(q => q.slice(1))
    setHistory(h => [current, ...h].slice(0, 50))
    setStats(s => s && {
      unreviewed: s.unreviewed - 1,
      reviewed: { ...s.reviewed, [tier]: (s.reviewed[tier] ?? 0) + 1 },
    })
    api.setTier(current.id, tier).catch(e => setError(String(e)))
  }, [current])

  const undo = useCallback(() => {
    const [last, ...rest] = history
    if (!last) return
    setHistory(rest)
    setQueue(q => [last, ...q.filter(c => c.id !== last.id)])
    api.setTier(last.id, 'candidate', false).then(() => api.triageStats().then(setStats))
  }, [history])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'z' || e.key === 'Backspace') { e.preventDefault(); undo(); return }
      const choice = KEYS[e.key]
      if (choice) { e.preventDefault(); decide(choice) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [decide, undo])

  const reviewedCount = stats ? Object.values(stats.reviewed).reduce((a, b) => a + (b ?? 0), 0) : 0
  const total = stats ? reviewedCount + stats.unreviewed : 0

  return (
    <div className="mx-auto max-w-2xl pt-2">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold">Triage channels</h1>
        {stats && (
          <div className="flex gap-3 text-sm text-muted tabular-nums">
            <span>{reviewedCount} / {total}</span>
            <span className="text-trusted">{stats.reviewed.trusted ?? 0} trusted</span>
            <span className="text-mixed">{stats.reviewed.mixed ?? 0} mixed</span>
            <span className="text-blocked">{stats.reviewed.blocked ?? 0} blocked</span>
          </div>
        )}
      </div>
      {total > 0 && (
        <div className="mb-5 h-1 overflow-hidden rounded-full bg-surface">
          <div className="h-full bg-accent transition-all" style={{ width: `${(reviewedCount / total) * 100}%` }} />
        </div>
      )}

      {error && <p className="mb-4 rounded-lg bg-surface p-3 text-sm text-blocked">{error}</p>}

      {loading ? (
        <p className="text-muted">Loading…</p>
      ) : !current ? (
        <Empty hasAny={total > 0} />
      ) : (
        <>
          <Card key={current.id} channel={current} preview={previews[current.id]} onSwipe={decide} />
          <div className="mt-4 grid grid-cols-4 gap-2">
            {CHOICES.map(c => (
              <button key={c.choice} onClick={() => decide(c.choice)}
                className="flex flex-col items-center rounded-xl bg-surface py-3 hover:bg-surface-hover active:scale-[.98]">
                <span className={`font-medium ${c.cls}`}>{c.label}</span>
                <span className="hidden text-xs text-muted md:block">{c.key.toUpperCase()}</span>
                <span className="text-xs text-muted md:hidden">{c.hint}</span>
              </button>
            ))}
          </div>
          <div className="mt-3 flex justify-between text-xs text-muted">
            <button onClick={undo} disabled={!history.length}
              className="rounded px-2 py-1 hover:bg-surface disabled:opacity-40">
              ↶ Undo <span className="hidden md:inline">(Z)</span>
            </button>
            <span className="py-1">Skip keeps it as a candidate (LLM-filtered later).</span>
          </div>
        </>
      )}
    </div>
  )
}

function Empty({ hasAny }: { hasAny: boolean }) {
  return (
    <div className="rounded-2xl bg-surface p-6 text-sm leading-relaxed">
      {hasAny ? (
        <p>All channels triaged. New ones from discovery will show up here.</p>
      ) : (
        <>
          <p className="mb-2 font-medium">No channels yet.</p>
          <p className="text-muted">Import your Google Takeout export (YouTube history as JSON, plus subscriptions):</p>
          <pre className="mt-2 overflow-x-auto rounded-lg bg-bg p-3 text-xs">uv run distill import-takeout ~/Downloads/Takeout</pre>
        </>
      )}
    </div>
  )
}

function Card({ channel: c, preview, onSwipe }: {
  channel: TriageChannel
  preview?: Preview
  onSwipe: (choice: Choice) => void
}) {
  const start = useRef<{ x: number; y: number } | null>(null)
  const [drag, setDrag] = useState({ x: 0, y: 0 })

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.pointerType === 'mouse') return
    start.current = { x: e.clientX, y: e.clientY }
  }
  const onPointerMove = (e: React.PointerEvent) => {
    if (!start.current) return
    setDrag({ x: e.clientX - start.current.x, y: e.clientY - start.current.y })
  }
  const onPointerUp = () => {
    if (!start.current) return
    const { x, y } = drag
    start.current = null
    setDrag({ x: 0, y: 0 })
    if (x > 90) onSwipe('trusted')
    else if (x < -90) onSwipe('blocked')
    else if (y < -90) onSwipe('mixed')
  }

  const hint = drag.x > 40 ? 'Trusted' : drag.x < -40 ? 'Block' : drag.y < -40 ? 'Mixed' : null
  const hintCls = drag.x > 40 ? 'text-trusted' : drag.x < -40 ? 'text-blocked' : 'text-mixed'
  const avatar = preview?.thumb_url ?? c.thumb_url

  return (
    <article
      onPointerDown={onPointerDown} onPointerMove={onPointerMove}
      onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
      style={{
        transform: `translate(${drag.x}px, ${Math.min(drag.y, 0)}px) rotate(${drag.x / 30}deg)`,
        transition: start.current ? 'none' : 'transform .2s',
        touchAction: 'pan-y',
      }}
      className="relative select-none rounded-2xl border border-line bg-bg p-5"
    >
      {hint && (
        <div className={`absolute right-5 top-5 rounded-lg border-2 border-current px-3 py-1 text-lg font-bold ${hintCls}`}>
          {hint}
        </div>
      )}
      <div className="flex items-center gap-4">
        {avatar ? (
          <img src={avatar} alt="" className="size-16 rounded-full bg-surface" draggable={false} />
        ) : (
          <div className="grid size-16 place-items-center rounded-full bg-surface text-2xl font-semibold text-muted">
            {c.title.slice(0, 1)}
          </div>
        )}
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold">
            <a href={`https://www.youtube.com/channel/${c.id}`} target="_blank" rel="noreferrer" className="hover:underline">
              {c.title}
            </a>
          </h2>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted">
            <span>Watched {c.watch_count}×</span>
            <span>{c.watches_180d} in last 6 mo</span>
            <span>last {timeAgo(c.last_watched_at)}</span>
            {c.is_subscribed ? <span className="text-fg">Subscribed</span> : null}
          </div>
        </div>
      </div>

      {c.watched_titles.length > 0 && (
        <section className="mt-5">
          <h3 className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted">You watched</h3>
          <ul className="space-y-1 text-sm">
            {c.watched_titles.map(t => <li key={t} className="line-clamp-1">{t}</li>)}
          </ul>
        </section>
      )}

      <section className="mt-5">
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">
          Latest uploads
          {preview && preview.shorts_share > 0.5 && (
            <span className="ml-2 normal-case tracking-normal text-mixed">
              mostly Shorts ({Math.round(preview.shorts_share * 100)}%)
            </span>
          )}
        </h3>
        {!preview ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {[0, 1, 2].map(i => (
              <div key={i} className={`aspect-video animate-pulse rounded-lg bg-surface ${i === 2 ? 'hidden sm:block' : ''}`} />
            ))}
          </div>
        ) : preview.latest.length === 0 ? (
          <p className="text-sm text-muted">No recent long-form uploads.</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {preview.latest.slice(0, 3).map((u, i) => (
              // Two on phones so the triage buttons stay above the fold.
              <div key={u.id} className={`min-w-0 ${i === 2 ? 'hidden sm:block' : ''}`}>
                <img src={u.thumb_url ?? `https://i.ytimg.com/vi/${u.id}/mqdefault.jpg`} alt=""
                  className="aspect-video w-full rounded-lg bg-surface object-cover" draggable={false} />
                <p className="mt-1 line-clamp-2 text-xs leading-snug">{u.title}</p>
                <p className="text-[11px] text-muted">{timeAgo(u.published_at)}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </article>
  )
}
