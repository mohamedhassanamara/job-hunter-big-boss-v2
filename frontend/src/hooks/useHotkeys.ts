import { useEffect, useLayoutEffect, useRef } from 'react'

type Handler = (e: KeyboardEvent) => void

export interface HotkeyOptions {
  enabled?: boolean
  /** Fire even when focus is in an input/textarea (use for mod+k, escape). */
  allowInInputs?: boolean
  /** Fire even when a dialog/menu/popover is open. */
  allowInOverlay?: boolean
}

let pendingPrefix: { key: string; at: number } | null = null
const SEQUENCE_MS = 1200

function isEditable(target: EventTarget | null) {
  const el = target as HTMLElement | null
  if (!el) return false
  return (
    el.isContentEditable ||
    el.tagName === 'INPUT' ||
    el.tagName === 'TEXTAREA' ||
    el.tagName === 'SELECT'
  )
}

function overlayOpen() {
  return !!document.querySelector(
    '[role="dialog"][data-state="open"], [role="menu"][data-state="open"], [role="listbox"], [data-radix-popper-content-wrapper]',
  )
}

function comboOf(e: KeyboardEvent) {
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key.toLowerCase()
  return `${e.metaKey || e.ctrlKey ? 'mod+' : ''}${e.altKey ? 'alt+' : ''}${key}`
}

/**
 * Register keyboard shortcuts. Keys: "j", "shift+?"-style is not needed ("?" works),
 * "mod+k", "escape", "enter", and two-key sequences like "g t".
 */
export function useHotkeys(bindings: Record<string, Handler>, options: HotkeyOptions = {}) {
  const ref = useRef(bindings)
  useLayoutEffect(() => {
    ref.current = bindings
  })
  const { enabled = true, allowInInputs = false, allowInOverlay = false } = options

  useEffect(() => {
    if (!enabled) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.isComposing) return
      if (!allowInInputs && isEditable(e.target)) return
      if (!allowInOverlay && overlayOpen()) return
      const combo = comboOf(e)
      const now = Date.now()

      if (pendingPrefix && now - pendingPrefix.at < SEQUENCE_MS) {
        const seq = `${pendingPrefix.key} ${combo}`
        const handler = ref.current[seq]
        if (handler) {
          e.preventDefault()
          pendingPrefix = null
          handler(e)
          return
        }
      }
      const startsSequence = Object.keys(ref.current).some((k) => k.startsWith(`${combo} `))
      if (startsSequence) {
        pendingPrefix = { key: combo, at: now }
        return
      }
      const handler = ref.current[combo]
      if (handler) {
        e.preventDefault()
        handler(e)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [enabled, allowInInputs, allowInOverlay])
}
