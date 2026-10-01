import { toast } from 'sonner'
import { useSetAgency, type AgencyOverride } from '@/lib/queries/library'

const LABEL: Record<'employer' | 'agency', string> = { employer: 'an employer', agency: 'a recruiting agency' }

/** Mark a company as an employer or an agency (or back to the rule), with an Undo toast (8s). */
export function useAgencyAction() {
  const set = useSetAgency()
  const run = (company: { id: number; name: string }, value: AgencyOverride) =>
    set.mutate(
      { companyId: company.id, value },
      {
        onSuccess: (r) =>
          toast.success(value ? `${company.name} marked as ${LABEL[value]}` : `${company.name}: the agency rule decides again`, {
            duration: 8000,
            action: { label: 'Undo', onClick: () => set.mutate({ companyId: company.id, value: r.previous }) },
          }),
        onError: (e) => toast.error(e.message),
      },
    )
  return { run, pending: set.isPending }
}
