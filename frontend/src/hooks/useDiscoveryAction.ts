import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { keys } from '@/lib/queries/keys'
import { useDiscoveryStatus, useStartDiscovery } from '@/lib/queries/workflow'

/** Start a discovery run. Progress and the summary toast come from <DiscoveryWatcher/>. */
export function useDiscoveryAction() {
  const start = useStartDiscovery()
  const status = useDiscoveryStatus()
  const qc = useQueryClient()
  const running = !!status.data?.running

  const trigger = () => {
    if (running) return
    start.mutate(undefined, {
      onSuccess: () => {
        toast('Discovery started', { description: 'Pulling jobs from your enabled sources…' })
        void qc.invalidateQueries({ queryKey: keys.discoveryStatus })
      },
      onError: (e) => toast.error(e.message),
    })
  }
  return { trigger, pending: start.isPending || running }
}
