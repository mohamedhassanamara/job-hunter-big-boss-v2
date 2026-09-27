import { useCallback, useSyncExternalStore } from 'react'

/** "Hide scores while labeling": a per-browser preference, so labels stay independent of the
 * scorer's opinion. Kept in localStorage (a viewer convenience; falls back to off). */
const KEY = 'jobhunter.hideScores'
const EVENT = 'jobhunter:hide-scores'

let memory = false // used when storage is blocked (private mode)

function read(): boolean {
  try {
    const stored = window.localStorage.getItem(KEY)
    return stored === null ? memory : stored === '1'
  } catch {
    return memory
  }
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}

export function useHideScores(): [boolean, (hide: boolean) => void] {
  const hidden = useSyncExternalStore(subscribe, read, () => false)
  const set = useCallback((hide: boolean) => {
    memory = hide
    try {
      window.localStorage.setItem(KEY, hide ? '1' : '0')
    } catch {
      // Storage blocked: `memory` keeps it for this session.
    }
    window.dispatchEvent(new Event(EVENT))
  }, [])
  return [hidden, set]
}
