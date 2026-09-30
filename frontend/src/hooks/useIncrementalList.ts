import { useCallback, useEffect, useRef, useState } from 'react'

/** The nearest scrolling ancestor (the list's own container), so rootMargin applies to it. */
function scrollParent(node: HTMLElement): HTMLElement | null {
  for (let el = node.parentElement; el; el = el.parentElement) {
    const { overflowY } = getComputedStyle(el)
    if (overflowY === 'auto' || overflowY === 'scroll') return el
  }
  return null
}

/**
 * Render a long list a page at a time: the first `step` items, then more when the sentinel
 * scrolls into view (or when the selection moves past what is rendered, so j/k and ?job= links
 * keep working). Keeps pages like Discover (2,000+ jobs) light without a virtualisation library.
 */
export function useIncrementalList<T>(items: T[], { step = 100, mustInclude = -1 }: { step?: number; mustInclude?: number } = {}) {
  const [count, setCount] = useState(step)
  const observer = useRef<IntersectionObserver | null>(null)
  const needed = mustInclude >= 0 ? Math.ceil((mustInclude + 1) / step) * step : 0
  const shown = Math.min(items.length, Math.max(count, needed))

  useEffect(() => () => observer.current?.disconnect(), [])

  // A callback ref: the sentinel mounts and unmounts as the list grows or ends.
  const sentinel = useCallback(
    (node: HTMLElement | null) => {
      observer.current?.disconnect()
      if (!node) return
      observer.current = new IntersectionObserver(
        (entries) => {
          if (entries.some((e) => e.isIntersecting)) setCount((c) => Math.max(c, shown) + step)
        },
        { root: scrollParent(node), rootMargin: '600px' },
      )
      observer.current.observe(node)
    },
    [shown, step],
  )

  return { visible: items.slice(0, shown), hasMore: shown < items.length, remaining: items.length - shown, sentinel }
}
