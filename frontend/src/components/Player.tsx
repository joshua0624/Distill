import { useEffect, useRef } from 'react'
import { api } from '../api'

// Just enough of the YouTube IFrame API for our use.
interface YTPlayer {
  getCurrentTime(): number
  getDuration(): number
  destroy(): void
}
declare global {
  interface Window {
    YT?: { Player: new (el: HTMLElement, opts: object) => YTPlayer }
    onYouTubeIframeAPIReady?: () => void
  }
}

const PLAYING = 1
const PAUSED = 2
const ENDED = 0
const SAVE_EVERY_MS = 10_000

let apiReady: Promise<void> | null = null
function loadApi(): Promise<void> {
  apiReady ??= new Promise(resolve => {
    if (window.YT?.Player) return resolve()
    window.onYouTubeIframeAPIReady = () => resolve()
    const s = document.createElement('script')
    s.src = 'https://www.youtube.com/iframe_api'
    document.head.appendChild(s)
  })
  return apiReady
}

/**
 * Embedded YouTube player that saves watch position. Uses the regular
 * youtube.com embed (not youtube-nocookie) so a signed-in Premium session applies.
 * Remount with a new `key` to switch videos.
 */
export default function Player({ videoId, start, onEnded }: {
  videoId: string
  start: number
  onEnded: () => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const onEndedRef = useRef(onEnded)
  onEndedRef.current = onEnded

  useEffect(() => {
    let player: YTPlayer | null = null
    let timer: number | undefined
    let cancelled = false

    const position = () => {
      if (!player) return null
      const d = player.getDuration()
      return d > 0 ? { t: player.getCurrentTime(), d } : null
    }
    const save = () => {
      const p = position()
      if (p) api.saveProgress(videoId, p.t, p.d).catch(() => {})
    }
    const saveOnExit = () => {
      const p = position()
      if (p) api.saveProgressOnExit(videoId, p.t, p.d)
    }

    loadApi().then(() => {
      if (cancelled || !el.current || !window.YT) return
      player = new window.YT.Player(el.current, {
        videoId,
        width: '100%',
        height: '100%',
        playerVars: { autoplay: 1, rel: 0, playsinline: 1, start: Math.floor(start) },
        events: {
          onStateChange: (e: { data: number }) => {
            window.clearInterval(timer)
            if (e.data === PLAYING) timer = window.setInterval(save, SAVE_EVERY_MS)
            if (e.data === PAUSED) save()
            if (e.data === ENDED) {
              const d = player?.getDuration() ?? 0
              if (d > 0) api.saveProgress(videoId, d, d).catch(() => {})
              onEndedRef.current()
            }
          },
        },
      })
    })

    window.addEventListener('pagehide', saveOnExit)
    return () => {
      cancelled = true
      window.clearInterval(timer)
      window.removeEventListener('pagehide', saveOnExit)
      saveOnExit()
      player?.destroy()
    }
  }, [videoId, start])

  return (
    <div className="aspect-video w-full overflow-hidden bg-black md:rounded-xl">
      <div ref={el} className="size-full" />
    </div>
  )
}
