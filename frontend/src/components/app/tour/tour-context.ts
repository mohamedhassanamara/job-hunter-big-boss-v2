import { createContext, useContext } from 'react'
import type { Tour, TourId } from '@/features/tours/tours'

export interface TourContextValue {
  tour: Tour | null
  index: number
  starting: boolean
  start: (id: TourId) => void
  stop: () => void
  next: () => void
  back: () => void
}

export const TourContext = createContext<TourContextValue | null>(null)

export function useTour() {
  const ctx = useContext(TourContext)
  if (!ctx) throw new Error('useTour must be used inside TourProvider')
  return ctx
}
