import { useCallback, useEffect, useRef } from 'react'
import { useHotkeys } from './useHotkeys'

interface Options<Id extends string | number> {
  ids: Id[]
  selectedId: Id | null
  onSelect: (id: Id) => void
  onOpen?: (id: Id) => void
  /** Extra single-key actions on the selected item, e.g. { s: shortlist, d: dismiss }. */
  actions?: Record<string, (id: Id) => void>
  enabled?: boolean
}

/** j/k navigation + Enter/o open + per-item action keys, shared by all list views. */
export function useListKeyboard<Id extends string | number>({
  ids,
  selectedId,
  onSelect,
  onOpen,
  actions = {},
  enabled = true,
}: Options<Id>) {
  // Keys can arrive faster than React re-renders; track the selection synchronously so a
  // quick "k" then "s" acts on the row "k" moved to, not the stale one.
  const current = useRef(selectedId)
  useEffect(() => {
    current.current = selectedId
  }, [selectedId])

  const move = useCallback(
    (delta: number) => {
      if (!ids.length) return
      const sel = current.current
      const index = sel === null ? -1 : ids.indexOf(sel)
      const next = index === -1 ? (delta > 0 ? 0 : ids.length - 1) : index + delta
      const id = ids[Math.max(0, Math.min(ids.length - 1, next))]
      current.current = id
      onSelect(id)
    },
    [ids, onSelect],
  )

  // Keep the selected row visible.
  useEffect(() => {
    if (selectedId === null) return
    document
      .querySelector(`[data-row-id="${selectedId}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [selectedId])

  const bindings: Record<string, () => void> = {
    j: () => move(1),
    k: () => move(-1),
    arrowdown: () => move(1),
    arrowup: () => move(-1),
  }
  const withSelected = (fn: (id: Id) => void) => () => {
    const sel = current.current
    if (sel !== null) fn(sel)
  }
  if (onOpen) {
    bindings.enter = withSelected(onOpen)
    bindings.o = withSelected(onOpen)
  }
  for (const [key, fn] of Object.entries(actions)) bindings[key] = withSelected(fn)
  useHotkeys(bindings, { enabled })
}
