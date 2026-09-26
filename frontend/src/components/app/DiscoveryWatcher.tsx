import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { pluralize, runSummary, SOURCE_LABELS } from '@/lib/format'
import { invalidateWork, keys } from '@/lib/queries/keys'
import { useDiscoveryStatus } from '@/lib/queries/workflow'

/**
 * Mounted once in the shell. When a run (manual or scheduled) finishes, refresh the data and
 * show a summary toast — plus a warning linking to Settings if any source failed.
 */
export function DiscoveryWatcher() {
  const { data } = useDiscoveryStatus()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const wasRunning = useRef<boolean | null>(null)

  useEffect(() => {
    if (!data) return
    const finished = wasRunning.current === true && !data.running
    wasRunning.current = data.running
    if (!finished || !data.run) return

    invalidateWork(qc)
    void qc.invalidateQueries({ queryKey: keys.settings })
    void qc.invalidateQueries({ queryKey: keys.sources })

    const run = data.run
    toast.success(run.trigger === 'scheduled' ? 'Scheduled discovery finished' : 'Discovery finished', {
      description: runSummary(run.totals),
      duration: 8000,
      action: run.totals.new ? { label: 'Review', onClick: () => navigate('/discover') } : undefined,
    })
    const failed = run.sources.filter((s) => s.status === 'failed')
    if (failed.length) {
      toast.warning(`${pluralize(failed.length, 'source')} failed`, {
        description: failed.map((s) => SOURCE_LABELS[s.source]).join(', '),
        duration: 10000,
        action: { label: 'Details', onClick: () => navigate('/settings?section=sources') },
      })
    }
  }, [data, qc, navigate])

  return null
}
