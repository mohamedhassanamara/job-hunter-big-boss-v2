import { toast } from 'sonner'
import { usePatchApplication, useTriage } from '@/lib/queries/jobs'

interface TriageTarget {
  jobId: number
  title: string
  company: string
}

/** Shortlist / dismiss with toast + Undo. Shared by Discover, Pipeline table and Job page. */
export function useTriageActions() {
  const triage = useTriage()
  const patch = usePatchApplication()

  const run = (target: TriageTarget, action: 'shortlist' | 'dismiss', onDone?: () => void) => {
    triage.mutate(
      { jobId: target.jobId, action },
      {
        onSuccess: (item) => {
          onDone?.()
          toast.success(action === 'shortlist' ? 'Shortlisted' : 'Dismissed', {
            description: `${target.title} · ${target.company}`,
            duration: 8000,
            action: {
              label: 'Undo',
              onClick: () =>
                patch.mutate(
                  { id: item.application.id, patch: { stage: 'new' } },
                  {
                    onSuccess: () => toast('Moved back to New'),
                    onError: (e) => toast.error(e.message),
                  },
                ),
            },
          })
        },
        onError: (e) => toast.error(e.message),
      },
    )
  }

  return {
    shortlist: (t: TriageTarget, onDone?: () => void) => run(t, 'shortlist', onDone),
    dismiss: (t: TriageTarget, onDone?: () => void) => run(t, 'dismiss', onDone),
    pending: triage.isPending,
  }
}
