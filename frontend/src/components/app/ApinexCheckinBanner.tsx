import { ExternalLink, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useApinexCheckedIn, useApinexStatus } from '@/lib/queries/workflow'
import { cn } from '@/lib/utils'

/** APInex answered HTTP 402 ("Daily check-in required"). Scoring keeps falling back to Ollama; CV
 * generation fails with the Retry panel. The check-in itself is yours to do on their site. */
export function ApinexCheckinBanner({ className }: { className?: string }) {
  const { data } = useApinexStatus()
  const checkedIn = useApinexCheckedIn()
  if (!data?.needs_checkin) return null
  return (
    <div role="status" className={cn('flex flex-wrap items-center gap-3 border border-tone-amber-border bg-warning-bg px-4 py-2.5 text-sm text-warning-fg', className)} data-tour="apinex-checkin">
      <TriangleAlert className="size-4 shrink-0" />
      <p className="min-w-0 flex-1">
        <span className="font-medium">APInex needs the daily check-in.</span> <span className="text-fg-muted">Scoring keeps falling back to Ollama; CV drafts fail until you check in.</span>
      </p>
      <Button size="sm" variant="secondary" asChild>
        <a href={data.url} target="_blank" rel="noreferrer">
          <ExternalLink />
          Open apinex.bond
        </a>
      </Button>
      <Button size="sm" variant="ghost" onClick={() => checkedIn.mutate()} disabled={checkedIn.isPending}>
        I checked in
      </Button>
    </div>
  )
}
