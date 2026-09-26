import { useCallback, useEffect } from 'react'
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
  const move = useCallback(
    (delta: number) => {
      if (!ids.length) return
      const index = selectedId === null ? -1 : ids.indexOf(selectedId)
      const next = index === -1 ? (delta > 0 ? 0 : ids.length - 1) : index + delta
      onSelect(ids[Math.max(0, Math.min(ids.length - 1, next))])
    },
    [ids, selectedId, onSelect],
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
  if (onOpen) {
    bindings.enter = () => selectedId !== null && onOpen(selectedId)
    bindings.o = () => selectedId !== null && onOpen(selectedId)
  }
  for (const [key, fn] of Object.entries(actions)) {
    bindings[key] = () => selectedId !== null && fn(selectedId)
  }
  useHotkeys(bindings, { enabled })
}
