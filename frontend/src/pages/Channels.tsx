import { useEffect, useState } from 'react'
import { api, type Channel, type Tier } from '../api'
import { timeAgo } from '../utils'

const TIERS: { tier: Tier; label: string; cls: string }[] = [
  { tier: 'trusted', label: 'Trusted', cls: 'text-trusted' },
  { tier: 'mixed', label: 'Mixed', cls: 'text-mixed' },
  { tier: 'candidate', label: 'Skipped', cls: 'text-muted' },
  { tier: 'blocked', label: 'Blocked', cls: 'text-blocked' },
]

export default function Channels() {
  const [tier, setTier] = useState<Tier>('trusted')
  const [channels, setChannels] = useState<Channel[] | null>(null)

  useEffect(() => {
    setChannels(null)
    api.channels(tier).then(setChannels)
  }, [tier])

  const move = async (c: Channel, to: Tier) => {
    await api.setTier(c.id, to)
    setChannels(cs => cs?.filter(x => x.id !== c.id) ?? null)
  }

  return (
    <div className="pt-2">
      <h1 className="mb-3 text-xl font-semibold">Channels</h1>
      <div className="mb-4 flex gap-2 overflow-x-auto">
        {TIERS.map(t => (
          <button key={t.tier} onClick={() => setTier(t.tier)}
            className={`shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium ${
              tier === t.tier ? 'bg-fg text-bg' : 'bg-surface hover:bg-surface-hover'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {!channels ? (
        <p className="text-muted">Loading…</p>
      ) : channels.length === 0 ? (
        <p className="text-muted">No channels here yet.</p>
      ) : (
        <ul className="divide-y divide-line">
          {channels.map(c => (
            <li key={c.id} className="flex items-center gap-3 py-2.5">
              {c.thumb_url ? (
                <img src={c.thumb_url} alt="" className="size-9 rounded-full bg-surface" />
              ) : (
                <div className="grid size-9 place-items-center rounded-full bg-surface text-sm text-muted">
                  {c.title.slice(0, 1)}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{c.title}</p>
                <p className="text-xs text-muted">
                  Watched {c.watch_count}× · last {timeAgo(c.last_watched_at)}
                </p>
              </div>
              <select value={c.tier} onChange={e => move(c, e.target.value as Tier)}
                aria-label={`Tier for ${c.title}`}
                className="rounded-lg bg-surface px-2 py-1.5 text-sm">
                {TIERS.map(t => <option key={t.tier} value={t.tier}>{t.label}</option>)}
              </select>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
