export interface ContentItem {
  id: string
  type: 'video' | 'post'
  title: string
  source_id: string
  source_name: string
  url: string
  thumbnail_url: string | null
  description: string | null
  duration: number | null       // seconds, videos only
  reddit_score: number | null
  body: string | null           // Reddit post body preview
  published_at: string          // ISO timestamp
  fetched_at: string
  is_read: number               // 0 | 1
  relevance_score: number | null
  summary: string | null
  is_low_density: number | null  // 0 | 1 | null
  scored_at: string | null
  is_discovery: number          // 0 | 1
  discovery_topic: string | null
  is_saved: number              // 0 | 1
}
