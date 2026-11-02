import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type FeedVideo } from '../api'
import VideoCard from '../components/VideoCard'

const PAGE = 48

export default function Home() {
  const [videos, setVideos] = useState<FeedVideo[] | null>(null)
  const [done, setDone] = useState(false)
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

  const hide = (id: string) => {
    setVideos(vs => vs?.filter(v => v.id !== id) ?? null)
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
      <div className="grid gap-x-4 gap-y-8 pt-2 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {videos.map(v => <VideoCard key={v.id} v={v} onHide={() => hide(v.id)} />)}
      </div>
      <div ref={sentinel} className="h-px" />
      {done && <p className="py-10 text-center text-sm text-muted">That's everything from your channels.</p>}
    </>
  )
}
