/** Per-track skill rules as text lines, so they can be edited in a textarea.
 * Display: "Mobile | Backend & Data Engineering = Backend". Keep: "Mobile | Core Languages = Kotlin, Swift". */

export type TrackTable<T> = Record<string, Record<string, T>>

export function formatRules<T extends string | string[]>(table: TrackTable<T> | undefined): string {
  return Object.entries(table ?? {})
    .flatMap(([track, rules]) => Object.entries(rules).map(([group, v]) => `${track} | ${group} = ${Array.isArray(v) ? v.join(', ') : v}`))
    .join('\n')
}

export function parseRules<T extends string | string[]>(text: string, list: boolean): TrackTable<T> {
  const out: TrackTable<T> = {}
  for (const line of text.split('\n')) {
    const m = /^\s*(.+?)\s*\|\s*(.+?)\s*=\s*(.+?)\s*$/.exec(line)
    if (!m) continue
    const [, track, group, value] = m
    const v = (list ? value.split(',').map((x) => x.trim()).filter(Boolean) : value) as T
    out[track] = { ...out[track], [group]: v }
  }
  return out
}
