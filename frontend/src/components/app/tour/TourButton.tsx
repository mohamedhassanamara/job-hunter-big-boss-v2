import { Compass } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { TourId } from '@/features/tours/tours'
import { useTour } from './tour-context'

/** Secondary "See how it works" action for empty states. */
export function TourButton({ tour, label = 'See how it works', onStart }: { tour: TourId; label?: string; onStart?: () => void }) {
  const { start, starting } = useTour()
  return (
    <Button size="sm" variant="ghost" onClick={() => {
        onStart?.()
        start(tour)
      }} disabled={starting}>
      <Compass />
      {label}
    </Button>
  )
}
