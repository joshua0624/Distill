import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type FeedVideo, type Rating, type Tier, type VideoDetail } from '../api'
import Player from '../components/Player'
import SaveButton from '../components/SaveButton'
import { ChannelAvatar, Thumb, VideoRow } from '../components/VideoCard'
import { compact, discoveredVia, timeAgo } from '../utils'

/** Resume where I left off, unless I'd basically finished it. */
function resumeFrom(v: VideoDetail): number {
  if (!v.position_s || (v.watched_pct ?? 0) >= 95) return 0
  return v.position_s > 5 ? v.position_s : 0
}

export default function Watch() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [video, setVideo] = useState<VideoDetail | null>(null)
  const [queue, setQueue] = useState<FeedVideo[]>([])
  const [ended, setEnded] = useState(false)
  const [missing, setMissing] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [replays, setReplays] = useState(0)

  const loadQueue = useCallback(() => api.queue().then(setQueue).catch(() => {}), [])

  useEffect(() => {
    setVideo(null)
    setEnded(false)
    setMissing(false)
    setExpanded(false)
    setReplays(0)
    window.scrollTo(0, 0)
    api.video(id).then(setVideo).catch(() => setMissing(true))
    loadQueue()
  }, [id, loadQueue])

  // Computed once per video so later progress refreshes don't restart the player.
  const start = useMemo(() => (video ? resumeFrom(video) : 0), [video?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const next = queue.find(q => q.id !== id)

  const onEnded = useCallback(() => {
    setEnded(true)
    // Finished videos leave the queue.
    setVideo(v => v && { ...v, in_queue: 0 })
    api.removeFromQueue(id).then(loadQueue).catch(() => {})
  }, [id, loadQueue])

  if (missing) {
    return (
      <div className="mx-auto mt-10 max-w-md text-center text-sm text-muted">
        <p className="mb-2 text-base text-fg">This video isn't in Distill.</p>
        <Link to="/" className="underline">Back to Home</Link>
      </div>
    )
  }

  return (
    <div className="mx-auto grid max-w-[1700px] gap-6 pt-0 md:pt-2 lg:grid-cols-[minmax(0,1fr)_400px]">
      <div className="min-w-0">
        <div className="relative -mx-4 md:mx-0">
          {video ? (
            // Replay remounts the player from 0 rather than revealing YouTube's own end screen.
            <Player key={`${video.id}-${replays}`} videoId={video.id} start={replays ? 0 : start} onEnded={onEnded} />
          ) : (
            <div className="aspect-video w-full animate-pulse bg-surface md:rounded-xl" />
          )}
          {ended && (
            <EndScreen next={next} onReplay={() => { setEnded(false); setReplays(r => r + 1) }}
              onNext={() => next && navigate(`/watch/${next.id}`)} />
          )}
        </div>

        {video && (
          <>
            <h1 className="mt-3 text-lg font-semibold leading-snug md:text-xl">{video.title}</h1>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <div className="flex min-w-0 flex-1 items-center gap-3">
                <ChannelAvatar v={video} size="size-10" />
                <div className="min-w-0">
                  <p className="truncate font-medium">{video.channel_title}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <RatingButtons key={video.id} id={video.id} initial={video.rating} />
                <SaveButton key={`${video.id}-${video.in_queue}`} v={video} label onChange={loadQueue} />
                <a href={`https://www.youtube.com/watch?v=${video.id}`} target="_blank" rel="noreferrer"
                  className="rounded-full bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-hover">
                  YouTube ↗
                </a>
              </div>
            </div>
            {video.tier === 'candidate' && (
              <NewChannel video={video} onTier={tier => setVideo(v => v && { ...v, tier })} />
            )}
            <div className="mt-3 rounded-xl bg-surface p-3 text-sm">
              <p className="font-medium">
                {video.views != null && `${compact(video.views)} views · `}{timeAgo(video.published_at)}
              </p>
              {video.description && (
                <>
                  <p className={`mt-1 whitespace-pre-line break-words ${expanded ? '' : 'line-clamp-3'}`}>
                    {video.description}
                  </p>
                  <button onClick={() => setExpanded(e => !e)} className="mt-1 font-medium">
                    {expanded ? 'Show less' : '...more'}
                  </button>
                </>
              )}
            </div>
          </>
        )}
      </div>

      <aside className="min-w-0">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="font-semibold">Watch later</h2>
          <Link to="/later" className="text-sm text-muted hover:text-fg">
            {queue.length} video{queue.length === 1 ? '' : 's'}
          </Link>
        </div>
        {queue.length === 0 ? (
          <p className="rounded-xl bg-surface p-4 text-sm text-muted">
            Nothing queued. Save videos with the clock icon and they'll line up here.
          </p>
        ) : (
          <div className="space-y-1">
            {queue.map(q => <VideoRow key={q.id} v={q} active={q.id === id} />)}
          </div>
        )}
      </aside>
    </div>
  )
}

function EndScreen({ next, onNext, onReplay }: {
  next?: FeedVideo
  onNext: () => void
  onReplay: () => void
}) {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black/90 p-4 text-white md:rounded-xl">
      {next ? (
        <div className="flex w-full max-w-md flex-col items-center gap-3 text-center">
          <p className="text-sm text-white/70">Up next from Watch later</p>
          <button onClick={onNext} className="w-full max-w-xs">
            <Thumb v={next} className="hidden sm:block" />
            <p className="mt-2 line-clamp-2 font-medium">{next.title}</p>
            <p className="text-sm text-white/70">{next.channel_title}</p>
          </button>
          <div className="flex gap-2">
            <button onClick={onReplay} className="rounded-full bg-white/15 px-4 py-2 text-sm hover:bg-white/25">Replay</button>
            <button onClick={onNext} className="rounded-full bg-white px-4 py-2 text-sm font-medium text-black">Play next</button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 text-center">
          <p className="text-lg font-medium">That's it.</p>
          <p className="text-sm text-white/70">Nothing left in Watch later.</p>
          <div className="flex gap-2">
            <button onClick={onReplay} className="rounded-full bg-white/15 px-4 py-2 text-sm hover:bg-white/25">Replay</button>
            <Link to="/" className="rounded-full bg-white px-4 py-2 text-sm font-medium text-black">Home</Link>
          </div>
        </div>
      )}
    </div>
  )
}

const THUMB = 'M7 10v11H4V10zM7 10l4-7a2 2 0 0 1 3 2l-1 5h5.5a2 2 0 0 1 2 2.4l-1.4 7A2 2 0 0 1 17.1 21H7'

function RatingButtons({ id, initial }: { id: string; initial: Rating }) {
  const [rating, setRating] = useState<Rating>(initial)
  const set = (r: Exclude<Rating, null>) => {
    const next = rating === r ? null : r
    const prev = rating
    setRating(next)
    api.rate(id, next).catch(() => setRating(prev))
  }
  return (
    <div className="flex overflow-hidden rounded-full bg-surface">
      {(['up', 'down'] as const).map(r => (
        <button key={r} onClick={() => set(r)} aria-pressed={rating === r}
          aria-label={r === 'up' ? 'I like this' : "I don't like this"}
          title={r === 'up' ? 'I like this' : "I don't like this"}
          className={`px-4 py-2 hover:bg-surface-hover ${r === 'down' ? 'border-l border-line' : ''}`}>
          <svg viewBox="0 0 24 24" className={`size-5 ${r === 'down' ? 'rotate-180' : ''}`}
            fill={rating === r ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.8"
            strokeLinejoin="round" aria-hidden><path d={THUMB} /></svg>
        </button>
      ))}
    </div>
  )
}

/** A discovered video: say where it came from and let me sort its channel on the spot. */
function NewChannel({ video, onTier }: { video: VideoDetail; onTier: (t: Tier) => void }) {
  const [done, setDone] = useState<Tier | null>(null)
  const choose = (tier: Tier) => {
    setDone(tier)
    api.setTier(video.channel_id, tier).then(() => { if (tier !== 'blocked') onTier(tier) })
      .catch(() => setDone(null))
  }
  const labels: Partial<Record<Tier, string>> = { trusted: 'Trusted', mixed: 'Mixed', blocked: 'Blocked' }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-line p-3 text-sm">
      <p className="min-w-0 flex-1">
        <span className="font-medium">New channel.</span>{' '}
        <span className="text-muted">{discoveredVia(video)}</span>
      </p>
      {done ? (
        <p className="text-muted">Added as {labels[done]}.</p>
      ) : (
        <div className="flex gap-2">
          <button onClick={() => choose('trusted')} className="rounded-full bg-surface px-3 py-1.5 font-medium text-trusted hover:bg-surface-hover">Trusted</button>
          <button onClick={() => choose('mixed')} className="rounded-full bg-surface px-3 py-1.5 font-medium text-mixed hover:bg-surface-hover">Mixed</button>
          <button onClick={() => choose('blocked')} className="rounded-full bg-surface px-3 py-1.5 font-medium text-blocked hover:bg-surface-hover">Block</button>
        </div>
      )}
    </div>
  )
}
