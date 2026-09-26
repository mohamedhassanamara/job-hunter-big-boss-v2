import { autoUpdate, flip, offset, shift, useFloating } from '@floating-ui/react-dom'
import { X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import type { Tour } from '@/features/tours/tours'

const PAD = 6
const FIND_TIMEOUT_MS = 4000

/** The overlay is remounted per step (keyed), so state always starts empty. */
function useTarget(selector: string | undefined) {
  const [el, setEl] = useState<HTMLElement | null>(null)
  useEffect(() => {
    if (!selector) return
    const started = performance.now()
    let raf = 0
    const find = () => {
      const found = document.querySelector<HTMLElement>(`[data-tour="${selector}"]`)
      if (found && found.getBoundingClientRect().width > 0) {
        found.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' })
        setEl(found)
      } else if (performance.now() - started < FIND_TIMEOUT_MS) {
        raf = requestAnimationFrame(find)
      }
    }
    raf = requestAnimationFrame(find)
    return () => cancelAnimationFrame(raf)
  }, [selector])
  return el
}

function useRect(el: HTMLElement | null) {
  const [rect, setRect] = useState<DOMRect | null>(null)
  useEffect(() => {
    if (!el) return
    const update = () => setRect(el.getBoundingClientRect())
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    const id = window.setInterval(update, 300) // layout shifts from async content
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
      window.clearInterval(id)
    }
  }, [el])
  return rect
}

/**
 * True while an app dialog/sheet is open (the tour card itself has no data-state). Polled rather
 * than observed: a MutationObserver here feeds back on the overlay's own re-renders.
 */
function useDialogOpen() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const id = window.setInterval(() => {
      const next = !!document.querySelector('[role="dialog"][data-state="open"]')
      setOpen((prev) => (prev === next ? prev : next))
    }, 250)
    return () => window.clearInterval(id)
  }, [])
  return open
}

export function TourOverlay({
  tour,
  index,
  onNext,
  onBack,
  onClose,
}: {
  tour: Tour
  index: number
  onNext: () => void
  onBack: () => void
  onClose: () => void
}) {
  const step = tour.steps[index]
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (step.route && location.pathname + location.search !== step.route) navigate(step.route)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when the step changes
  }, [step])

  const el = useTarget(step.target)
  const rect = useRect(el)
  const { refs, floatingStyles } = useFloating({
    placement: step.placement ?? 'bottom',
    middleware: [offset(PAD + 10), flip({ padding: 12 }), shift({ padding: 12 })],
    whileElementsMounted: autoUpdate,
  })

  useEffect(() => {
    refs.setReference(el)
  }, [el, refs])

  // Capture phase: tour keys win over page shortcuts and focused widgets (e.g. a tooltip's
  // own Escape handling), and don't also trigger the page's Escape (closing a panel).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // A dialog/sheet opened during the tour owns the keyboard (Esc closes it, not the tour).
      if (document.querySelector('[role="dialog"][data-state="open"]')) return
      const el = e.target as HTMLElement | null
      const typing = !!el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))
      const handlers: Record<string, () => void> = {
        Escape: onClose,
        ...(typing ? {} : { ArrowRight: onNext, ArrowLeft: onBack }),
      }
      const handler = handlers[e.key]
      if (!handler) return
      e.preventDefault()
      e.stopPropagation()
      handler()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [onClose, onNext, onBack])

  const dialogOpen = useDialogOpen()
  const last = index === tour.steps.length - 1
  // Clamp the spotlight to the viewport (big targets like the board).
  const spot = rect && {
    top: Math.max(rect.top - PAD, 4),
    left: Math.max(rect.left - PAD, 4),
    width: Math.min(rect.width + PAD * 2, window.innerWidth - Math.max(rect.left - PAD, 4) - 4),
    height: Math.min(rect.height + PAD * 2, window.innerHeight - Math.max(rect.top - PAD, 4) - 4),
  }

  // Step aside while the user works in a dialog or sheet opened from the tour.
  if (dialogOpen) return null

  return (
    <>
      {spot ? (
        <div
          aria-hidden
          className="pointer-events-none fixed z-[60] rounded-lg outline-2 outline-primary"
          style={{ ...spot, boxShadow: '0 0 0 9999px var(--overlay)' }}
        />
      ) : (
        <div aria-hidden className="pointer-events-none fixed inset-0 z-[60] bg-overlay" />
      )}
      <div
        ref={refs.setFloating}
        role="dialog"
        aria-label={`${tour.title} tour: ${step.title}`}
        style={el ? floatingStyles : undefined}
        className={
          el
            ? 'z-[63] w-80 rounded-xl border border-border bg-surface-raised p-4 shadow-lg'
            : 'fixed top-1/3 left-1/2 z-[63] w-80 -translate-x-1/2 rounded-xl border border-border bg-surface-raised p-4 shadow-lg'
        }
      >
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="text-2xs font-medium text-primary">
            {tour.title} · {index + 1} / {tour.steps.length}
          </span>
          <button
            onClick={onClose}
            className="rounded-md p-0.5 text-fg-subtle hover:bg-surface-hover hover:text-fg"
            aria-label="Exit tour"
          >
            <X className="size-4" />
          </button>
        </div>
        <p className="text-md font-semibold tracking-tight">{step.title}</p>
        <p className="mt-1 text-sm text-fg-muted">{step.body}</p>
        <div className="mt-4 flex items-center gap-2">
          <div className="flex gap-1" aria-hidden>
            {tour.steps.map((_, i) => (
              <span
                key={i}
                className={i === index ? 'h-1.5 w-4 rounded-full bg-primary' : 'size-1.5 rounded-full bg-border-strong'}
              />
            ))}
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            {index > 0 && (
              <Button size="sm" variant="ghost" onClick={onBack}>
                Back
              </Button>
            )}
            <Button size="sm" variant="default" onClick={onNext}>
              {last ? 'Done' : 'Next'}
              {!last && <Kbd className="border-transparent bg-primary-hover text-primary-fg">→</Kbd>}
            </Button>
          </div>
        </div>
      </div>
    </>
  )
}
