import { Compass, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useTour } from './tour-context'

/** Persistent banner while a tour runs, so sample data can't be mistaken for real data. */
export function TourStrip() {
  const { tour, stop } = useTour()
  if (!tour) return null
  return (
    <div
      role="status"
      className="relative z-[62] flex h-9 shrink-0 items-center gap-2 border-b border-tone-blue-border bg-info-bg px-4 text-sm text-info-fg"
    >
      <Compass className="size-4" />
      <span className="font-medium">Tour: {tour.title}</span>
      <span className="text-info-fg/80">· Sample data. Nothing here is real, and changes are thrown away.</span>
      <Button size="xs" variant="ghost" className="ml-auto text-info-fg hover:bg-info-bg hover:text-info-fg" onClick={stop}>
        <X />
        Exit tour
      </Button>
    </div>
  )
}
