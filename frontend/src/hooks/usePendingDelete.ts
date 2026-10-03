import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

/** Delete with an Undo toast: the row hides at once and is only deleted when the toast
 * expires (8s), so Undo needs nothing from the server. */
export function usePendingDelete(commit: (id: number) => void) {
  const [hidden, setHidden] = useState<Set<number>>(new Set())
  const timers = useRef(new Map<number, number>())
  const commitRef = useRef(commit)
  useEffect(() => {
    commitRef.current = commit
  })
  useEffect(() => {
    const pending = timers.current
    return () => {
      // Leaving the page: finish what was deleted (the toast can't be undone from elsewhere).
      for (const [id, timer] of pending) {
        window.clearTimeout(timer)
        commitRef.current(id)
      }
      pending.clear()
    }
  }, [])

  const remove = (id: number, label: string) => {
    setHidden((h) => new Set(h).add(id))
    const timer = window.setTimeout(() => {
      timers.current.delete(id)
      commitRef.current(id)
    }, 8000)
    timers.current.set(id, timer)
    toast(`${label} deleted`, {
      duration: 8000,
      action: {
        label: 'Undo',
        onClick: () => {
          window.clearTimeout(timers.current.get(id))
          timers.current.delete(id)
          setHidden((h) => {
            const next = new Set(h)
            next.delete(id)
            return next
          })
        },
      },
    })
  }
  return { hidden, remove }
}
