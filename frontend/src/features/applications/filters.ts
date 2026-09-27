import { useMemo } from 'react'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import type { TrackingFilters } from '@/lib/types'

/** Applied/Stats filters live in the URL (?track=&country=&source=&stage=&from=&to=). */
export function useTrackingFilters() {
  const url = useSearchParamState()
  const track = url.getAll('track')
  const country = url.getAll('country')
  const source = url.getAll('source')
  const stage = url.getAll('stage')
  const start = url.get('from') ?? ''
  const end = url.get('to') ?? ''
  // A stable object while the URL doesn't change (query keys and effects compare by reference).
  const key = JSON.stringify({ track, country, source, stage, start, end })
  const filters = useMemo(() => JSON.parse(key) as TrackingFilters, [key])
  const active = track.length + country.length + source.length + stage.length > 0 || !!start || !!end
  const set = (patch: Partial<Record<'track' | 'country' | 'source' | 'stage' | 'from' | 'to', string | string[] | null>>) =>
    url.set({ ...patch, app: null })
  const clear = () => url.set({ track: null, country: null, source: null, stage: null, from: null, to: null, app: null })
  return { filters, active, set, clear }
}
