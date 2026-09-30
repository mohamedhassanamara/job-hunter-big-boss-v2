import { RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { CopilotChat } from '@/components/app/copilot/CopilotChat'
import { ErrorState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { useClearJobCopilot, useJobCopilot } from '@/lib/queries/copilot'
import type { JobDetail } from '@/lib/types'

/** The job's Copilot: a conversation saved per job, with the job's data as context. */
export function CopilotSheet({ job, open, onOpenChange }: { job: JobDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const appId = job.application.id
  const thread = useJobCopilot(appId, open)
  const clear = useClearJobCopilot()
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent title="Copilot" description={`${job.title} · ${job.company.name}`} className="max-w-[640px]">
        <div className="flex min-h-0 flex-1 flex-col" data-tour="job-copilot">
          {thread.isPending ? (
            <div className="space-y-3 p-5">
              <Skeleton className="h-16" />
              <Skeleton className="h-24" />
            </div>
          ) : thread.error ? (
            <ErrorState error={thread.error} onRetry={() => thread.refetch()} />
          ) : (
            <>
              {thread.data.messages.length > 0 && (
                <div className="flex justify-end border-b border-border px-5 py-1.5">
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => clear.mutate(appId, { onSuccess: () => toast.success('New conversation (the old one is kept)') })}
                  >
                    <RotateCcw />
                    New conversation
                  </Button>
                </div>
              )}
              <CopilotChat thread={thread.data} placeholder="Ask about this job: the interview, your CV, a message to write…" />
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
