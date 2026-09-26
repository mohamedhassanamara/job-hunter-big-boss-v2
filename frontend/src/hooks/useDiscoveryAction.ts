import { toast } from 'sonner'
import { pluralize } from '@/lib/format'
import { useRunDiscovery } from '@/lib/queries/workflow'

export function useDiscoveryAction() {
  const run = useRunDiscovery()
  const trigger = () =>
    toast.promise(run.mutateAsync(), {
      loading: 'Running discovery across enabled sources…',
      success: (r) =>
        r.new_jobs
          ? `${pluralize(r.new_jobs, 'new job')} found and scored`
          : 'No new jobs this time',
      error: (e: Error) => `Discovery failed: ${e.message}`,
    })
  return { trigger, pending: run.isPending }
}
