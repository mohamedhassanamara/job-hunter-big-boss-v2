import { useCallback, useMemo, useRef, useState } from 'react'

/** Row checkboxes for a list: toggle one, shift-click a range from the last one touched, all / none.
 * Ids that leave the list drop out of the selection. */
export function useRowSelection(ids: number[]) {
  const [picked, setPicked] = useState<Set<number>>(new Set())
  const anchor = useRef<number | null>(null)

  // Only rows still in the list count; order follows the list, not the clicks.
  const selected = useMemo(() => ids.filter((id) => picked.has(id)), [ids, picked])

  const toggle = useCallback(
    (id: number, shift = false) => {
      setPicked((prev) => {
        const next = new Set(prev)
        const from = anchor.current !== null ? ids.indexOf(anchor.current) : -1
        const to = ids.indexOf(id)
        if (shift && from !== -1 && to !== -1) {
          const [lo, hi] = from < to ? [from, to] : [to, from]
          const on = !prev.has(id) // the range takes the state this click gives the clicked row
          for (const rid of ids.slice(lo, hi + 1)) {
            if (on) next.add(rid)
            else next.delete(rid)
          }
        } else if (next.has(id)) next.delete(id)
        else next.add(id)
        return next
      })
      anchor.current = id
    },
    [ids],
  )

  return {
    selected,
    has: (id: number) => picked.has(id),
    toggle,
    selectAll: () => setPicked(new Set(ids)),
    selectNone: () => {
      setPicked(new Set())
      anchor.current = null
    },
  }
}
