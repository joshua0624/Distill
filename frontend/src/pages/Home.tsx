import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type FeedVideo } from '../api'
import VideoCard from '../components/VideoCard'
import { discoveredVia } from '../utils'

const PAGE = 48

export default function Home() {
  const [videos, setVideos] = useState<FeedVideo[] | null>(null)
  const [done, setDone] = useState(false)
  const [discovery, setDiscovery] = useState<FeedVideo[]>([])
  const loading = useRef(false)
  const sentinel = useRef<HTMLDivElement>(null)

  const loadMore = useCallback(async () => {
    if (loading.current || done) return
    loading.current = true
    try {
      const offset = videos?.length ?? 0
      const page = await api.feed(offset, PAGE)
      setVideos(v => [...(v ?? []), ...page])
      if (page.length < PAGE) setDone(true)
    } catch {
      setVideos(v => v ?? [])
      setDone(true)
    } finally {
      loading.current = false
    }
  }, [videos, done])

  useEffect(() => { if (!videos) loadMore() }, [videos, loadMore])
  useEffect(() => { api.discovery().then(setDiscovery).catch(() => {}) }, [])

  const hide = (id: string) => {
    setVideos(vs => vs?.filter(v => v.id !== id) ?? null)
    setDiscovery(vs => vs.filter(v => v.id !== id))
    api.override(id, false).catch(() => {})
  }

  useEffect(() => {
    const el = sentinel.current
    if (!el || done) return
    const io = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting) loadMore()
    }, { rootMargin: '800px' })
    io.observe(el)
    return () => io.disconnect()
  }, [loadMore, done])

  if (!videos) return <p className="pt-4 text-muted">Loading…</p>
  if (videos.length === 0) {
    return (
      <div className="mx-auto mt-10 max-w-md text-center text-sm text-muted">
        <p className="mb-2 text-base text-fg">Nothing in your feed yet.</p>
        <p>
          <Link to="/triage" className="text-fg underline">Triage some channels</Link>, then run{' '}
          <code className="rounded bg-surface px-1.5 py-0.5">uv run distill ingest</code>.
        </p>
      </div>
    )
  }

  return (
    <>
      {discovery.length > 0 && (
        <section className="mb-8 pt-2">
          <div className="mb-3 flex items-baseline gap-2">
            <h2 className="text-lg font-semibold">Discovery</h2>
            <p className="text-sm text-muted">From channels you don't follow yet</p>
          </div>
          <div className="-mx-4 flex snap-x gap-4 overflow-x-auto px-4 pb-2 [scrollbar-color:var(--color-line)_transparent] [scrollbar-width:thin] md:-mx-0 md:px-0">
            {discovery.map(v => (
              <div key={v.id} className="w-72 shrink-0 snap-start sm:w-80">
                <VideoCard v={v} onHide={() => hide(v.id)} note={discoveredVia(v)} />
              </div>
            ))}
          </div>
        </section>
      )}
      <div className="grid gap-x-4 gap-y-8 pt-2 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {videos.map(v => <VideoCard key={v.id} v={v} onHide={() => hide(v.id)} />)}
      </div>
      <div ref={sentinel} className="h-px" />
      {done && <p className="py-10 text-center text-sm text-muted">That's everything from your channels.</p>}
    </>
  )
}
