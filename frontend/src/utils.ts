export function timeAgo(iso: string | null): string {
  if (!iso) return 'never'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  const units: [number, string][] = [
    [31536000, 'year'], [2592000, 'month'], [604800, 'week'],
    [86400, 'day'], [3600, 'hour'], [60, 'minute'],
  ]
  for (const [secs, name] of units) {
    const n = Math.floor(s / secs)
    if (n >= 1) return `${n} ${name}${n > 1 ? 's' : ''} ago`
  }
  return 'just now'
}

export function duration(s: number): string {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

export function compact(n: number | null): string {
  if (n == null) return ''
  return Intl.NumberFormat('en', { notation: 'compact' }).format(n)
}

const REASONS: Record<string, string> = {
  short: 'Shorts',
  too_short: 'Too short',
  live: 'Live now',
  upcoming: 'Upcoming',
  blocked_keyword: 'Blocked keyword',
  blocked_channel: 'Blocked channel',
  sport_rule_miss: 'Sport rule miss',
  pending_llm: 'Waiting to be classified',
  too_few_views: 'Too few views (discovery)',
  llm_error: "Couldn't classify",
  override: 'Hidden by you',
}

/** Human label for a decision reason; rules.yaml reasons come as `rule:<name>`. */
export function reasonLabel(reason: string | null): string {
  if (!reason) return ''
  return reason.startsWith('rule:') ? reason.slice(5) : REASONS[reason] ?? reason
}

/** Where a discovered video came from, for the Discovery row and watch page. */
export function discoveredVia(v: { source: string; discovered_via: string | null }): string {
  const via = v.discovered_via ?? ''
  if (v.source === 'search') return `Search: ${via}`
  if (v.source === 'adjacent') return via.charAt(0).toUpperCase() + via.slice(1)
  if (v.source === 'llm') return via.replace(/^suggested: /, 'Suggested: ')
  return via || 'Discovery'
}
