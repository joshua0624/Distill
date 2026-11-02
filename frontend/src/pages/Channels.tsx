import { useCallback, useEffect, useState } from 'react'
import { api, type AddedChannel, type Channel, type ChannelChoice, type Suggestion, type Tier } from '../api'
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
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])

  useEffect(() => { api.suggestions().then(setSuggestions).catch(() => {}) }, [])

  const answer = (sg: Suggestion, accept: boolean) => {
    setSuggestions(ss => ss.filter(x => x.id !== sg.id))
    if (accept) api.setTier(sg.id, sg.kind === 'promote' ? 'trusted' : 'mixed')
    else api.dismissSuggestion(sg.id, sg.kind)
  }

  const load = useCallback(() => { api.channels(tier).then(setChannels) }, [tier])

  useEffect(() => {
    setChannels(null)
    load()
  }, [load])

  const move = async (c: Channel, to: Tier) => {
    await api.setTier(c.id, to)
    setChannels(cs => cs?.filter(x => x.id !== c.id) ?? null)
  }

  return (
    <div className="pt-2">
      <h1 className="mb-3 text-xl font-semibold">Channels</h1>
      <AddChannel onAdded={added => { if (added.tier === tier) load() }} />
      {suggestions.length > 0 && (
        <section className="mb-5 rounded-xl border border-line p-3">
          <h2 className="mb-2 text-sm font-semibold">Suggestions</h2>
          <ul className="space-y-2">
            {suggestions.map(sg => (
              <li key={sg.id} className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm">
                <p className="min-w-0 flex-1">
                  <span className="font-medium">{sg.title}</span>{' '}
                  <span className="text-muted">
                    {sg.kind === 'promote'
                      ? `· ${[sg.ups && `${sg.ups} 👍`, sg.finished && `${sg.finished} watched`].filter(Boolean).join(', ')} · move to Trusted?`
                      : `· ${sg.downs} 👎 · move to Mixed?`}
                  </span>
                </p>
                <div className="flex gap-2">
                  <button onClick={() => answer(sg, true)} className="rounded-full bg-fg px-3 py-1 text-xs font-medium text-bg">
                    {sg.kind === 'promote' ? 'Make Trusted' : 'Make Mixed'}
                  </button>
                  <button onClick={() => answer(sg, false)} className="rounded-full bg-surface px-3 py-1 text-xs hover:bg-surface-hover">
                    Not now
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
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

const LABEL: Record<Tier, string> = { trusted: 'Trusted', mixed: 'Mixed', blocked: 'Blocked', candidate: 'Skipped' }

/** Paste a channel or video link, an @handle, or a name, and add it straight to a tier. */
function AddChannel({ onAdded }: { onAdded: (c: AddedChannel) => void }) {
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState<Tier | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [choices, setChoices] = useState<ChannelChoice[]>([])

  const add = async (tier: Tier, what = query) => {
    if (!what.trim() || busy) return
    setBusy(tier)
    setMessage(null)
    try {
      const res = await api.addChannel(what, tier)
      if ('choices' in res) {
        setChoices(res.choices)
        return
      }
      const c = res
      setChoices([])
      const moved = c.previous_tier && c.previous_tier !== tier ? ` (was ${LABEL[c.previous_tier]})` : ''
      const plural = (n: number) => `${n} video${n === 1 ? '' : 's'}`
      const videos = tier === 'blocked' ? ''
        : [c.visible && `${plural(c.visible)} in your feed`, c.pending && `${plural(c.pending)} being classified`]
          .filter(Boolean).join(', ') || 'nothing from the last two weeks'
      setMessage({ ok: true, text: `Added ${c.title} as ${LABEL[tier]}${moved}${videos ? ` · ${videos}` : ''}.` })
      setQuery('')
      onAdded(c)
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : String(e) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <form onSubmit={e => { e.preventDefault(); add('trusted') }} className="mb-5">
      <div className="flex flex-wrap gap-2">
        <input value={query} onChange={e => setQuery(e.target.value)}
          placeholder="Channel link, video link, @handle or name"
          aria-label="Channel to add"
          className="min-w-0 flex-1 basis-64 rounded-lg border border-line bg-bg px-3 py-2 text-sm placeholder:text-muted" />
        <div className="flex gap-2">
          <button type="submit" disabled={!query.trim() || !!busy}
            className="rounded-lg bg-surface px-3 py-2 text-sm font-medium text-trusted hover:bg-surface-hover disabled:opacity-50">
            {busy === 'trusted' ? 'Adding…' : 'Add as Trusted'}
          </button>
          <button type="button" onClick={() => add('mixed')} disabled={!query.trim() || !!busy}
            className="rounded-lg bg-surface px-3 py-2 text-sm font-medium text-mixed hover:bg-surface-hover disabled:opacity-50">
            {busy === 'mixed' ? 'Adding…' : 'Add as Mixed'}
          </button>
        </div>
      </div>
      {message && (
        <p className={`mt-2 text-sm ${message.ok ? 'text-muted' : 'text-blocked'}`}>{message.text}</p>
      )}
      {choices.length > 0 && (
        <div className="mt-3 rounded-xl border border-line p-2">
          <p className="mb-1 px-1 text-xs text-muted">Which one?</p>
          <ul>
            {choices.map(ch => (
              <li key={ch.id} className="flex items-center gap-3 rounded-lg p-1.5">
                {ch.thumb_url
                  ? <img src={ch.thumb_url} alt="" className="size-9 shrink-0 rounded-full bg-surface" />
                  : <div className="size-9 shrink-0 rounded-full bg-surface" />}
                <div className="min-w-0 flex-1">
                  <a href={`https://www.youtube.com/channel/${ch.id}`} target="_blank" rel="noreferrer"
                    className="block truncate text-sm font-medium hover:underline">{ch.title}</a>
                  <p className="truncate text-xs text-muted">{ch.description || 'No description'}</p>
                </div>
                <button type="button" onClick={() => add('trusted', ch.id)} disabled={!!busy}
                  className="rounded-lg bg-surface px-2.5 py-1.5 text-xs font-medium text-trusted hover:bg-surface-hover disabled:opacity-50">
                  Trusted
                </button>
                <button type="button" onClick={() => add('mixed', ch.id)} disabled={!!busy}
                  className="rounded-lg bg-surface px-2.5 py-1.5 text-xs font-medium text-mixed hover:bg-surface-hover disabled:opacity-50">
                  Mixed
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </form>
  )
}
