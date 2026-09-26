import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { type TourId, TOURS, type Tour } from '@/features/tours/tours'
import { api, setWorkspace } from '@/lib/api'
import { TourContext, type TourContextValue } from './tour-context'
import { TourOverlay } from './TourOverlay'

/**
 * Runs guided tours against the sandbox workspace. Starting a tour rebuilds the sandbox,
 * switches every API call to it and clears the query cache; exiting switches back to the real
 * workspace and returns to where the user was.
 */
export function TourProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const [tour, setTour] = useState<Tour | null>(null)
  const [index, setIndex] = useState(0)
  const [starting, setStarting] = useState(false)
  const returnTo = useRef<string | null>(null)

  const start = useCallback(
    async (id: TourId) => {
      if (starting) return
      setStarting(true)
      if (!tour) returnTo.current = location.pathname + location.search
      setWorkspace('demo')
      qc.clear()
      try {
        await api.post('/sandbox/reset')
        const route = await TOURS[id].resolveRoute()
        navigate(route)
        setIndex(0)
        setTour(TOURS[id])
      } catch (e) {
        setWorkspace('real')
        qc.clear()
        toast.error(`Couldn't start the tour: ${(e as Error).message}`)
      } finally {
        setStarting(false)
      }
    },
    [starting, tour, location, qc, navigate],
  )

  const stop = useCallback(() => {
    setWorkspace('real')
    qc.clear()
    setTour(null)
    navigate(returnTo.current ?? '/')
    returnTo.current = null
    // Don't leave focus (and its tooltip) on whatever launched the tour: it would swallow the
    // next click on that control.
    window.setTimeout(() => (document.activeElement as HTMLElement | null)?.blur(), 0)
  }, [qc, navigate])

  const next = useCallback(() => {
    if (!tour) return
    if (index >= tour.steps.length - 1) stop()
    else setIndex((i) => i + 1)
  }, [tour, index, stop])

  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), [])

  const value = useMemo<TourContextValue>(
    () => ({ tour, index, starting, start: (id) => void start(id), stop, next, back }),
    [tour, index, starting, start, stop, next, back],
  )

  return (
    <TourContext.Provider value={value}>
      {children}
      {tour && (
        <TourOverlay
          key={`${tour.id}-${index}`}
          tour={tour}
          index={index}
          onNext={next}
          onBack={back}
          onClose={stop}
        />
      )}
    </TourContext.Provider>
  )
}
