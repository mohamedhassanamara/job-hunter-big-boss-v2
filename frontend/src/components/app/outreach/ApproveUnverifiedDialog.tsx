import { ShieldOff } from 'lucide-react'

/** The mark an unverified approval carries (visible in the draft, the queue and the job). */
export function UnverifiedBadge({ at, ignored }: { at?: string; ignored?: number }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm bg-warning-bg px-1.5 py-0.5 text-xs font-medium text-warning-fg">
      <ShieldOff className="size-3" />
      Approved without verification
      {at && <span className="font-normal"> · {new Date(at).toLocaleDateString()}</span>}
      {ignored ? <span className="font-normal"> · {ignored} ignored</span> : null}
    </span>
  )
}
