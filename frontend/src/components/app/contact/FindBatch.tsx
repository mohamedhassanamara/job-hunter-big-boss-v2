import { Square, UserRoundSearch } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { useBatchPreview, useFindContact } from '@/lib/queries/getContact'

interface Progress {
  done: number
  total: number
  current: string | null
  found: number
  failed: number
  credits: number
  usd: number
  stopped: boolean
  finished: boolean
}

const UNIT = { credits: 'credits', usd: '$' } as const

/** "Find contacts for this batch": the one-click waterfall, run for every shortlisted job
 * without a contact, one after another, after you have seen how many jobs and what it can spend.
 * It runs from this page (closing the tab stops it) and never picks a contact for a job:
 * what it finds lands in Contacts to get for you to use and verify. */
export function FindBatchButton({ className }: { className?: string }) {
  const [open, setOpen] = useState(false)
  const preview = useBatchPreview(open)
  const find = useFindContact()
  const [progress, setProgress] = useState<Progress | null>(null)
  const stop = useRef(false)
  const count = preview.data?.jobs.length ?? 0
  const running = progress !== null && !progress.finished

  const start = async () => {
    const jobs = preview.data?.jobs ?? []
    if (!jobs.length) return
    stop.current = false
    let p: Progress = { done: 0, total: jobs.length, current: null, found: 0, failed: 0, credits: 0, usd: 0, stopped: false, finished: false }
    setProgress(p)
    for (const job of jobs) {
      if (stop.current) break
      p = { ...p, current: `${job.company_name} · ${job.job_title}` }
      setProgress(p)
      try {
        const res = await find.mutateAsync({ appId: job.application_id })
        p = { ...p, credits: p.credits + res.credits, usd: p.usd + res.usd, found: p.found + (res.found_by || res.candidates.length ? 1 : 0) }
      } catch (e) {
        p = { ...p, failed: p.failed + 1 }
        toast.error(`${job.company_name}: ${(e as Error).message}`)
      }
      p = { ...p, done: p.done + 1 }
      setProgress(p)
    }
    setProgress({ ...p, current: null, stopped: stop.current, finished: true })
  }

  const close = () => {
    if (running) return
    setOpen(false)
    setProgress(null)
  }

  return (
    <>
      <Button size="sm" variant="secondary" className={className} onClick={() => setOpen(true)} data-tour="find-batch">
        <UserRoundSearch />
        Find contacts for this batch
      </Button>
      <Dialog open={open} onOpenChange={(o) => (o ? setOpen(true) : close())}>
        <DialogContent title="Find contacts for this batch" className="max-w-lg p-0">
          <div className="space-y-3 px-5 py-4">
            <h2 className="text-md font-semibold tracking-tight">Find contacts for this batch</h2>
            {progress ? (
              <div className="space-y-2 text-sm" aria-live="polite">
                <p>
                  {progress.finished ? (progress.stopped ? 'Stopped' : 'Done') : 'Searching'}: {progress.done} of {progress.total} jobs
                  {progress.current ? ` · ${progress.current}` : ''}
                </p>
                <div className="h-1.5 overflow-hidden rounded-full bg-border">
                  <div className="h-full bg-primary transition-all duration-300" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
                </div>
                <p className="text-fg-muted">
                  {progress.found} with people found · {progress.failed} failed · spent {progress.credits} credits and ${progress.usd.toFixed(2)}
                </p>
                {progress.finished && <p className="text-fg-muted">People found are on each company. Open Contacts to get to use and verify them: nothing is chosen for you.</p>}
              </div>
            ) : preview.isPending ? (
              <p className="text-sm text-fg-muted">Counting…</p>
            ) : preview.error ? (
              <p className="text-sm text-danger-fg">{preview.error.message}</p>
            ) : count === 0 ? (
              <p className="text-sm text-fg-muted">Every shortlisted job already has a contact, or the company is marked never or nobody found.</p>
            ) : (
              <>
                <p className="text-sm text-fg-muted">
                  This runs the contact waterfall (cache, Hunter, Prospeo, Apollo, Apify, local pattern) for <span className="font-medium text-fg">{count} shortlisted job{count === 1 ? '' : 's'}</span> without a contact, at{' '}
                  {preview.data?.companies} compan{preview.data?.companies === 1 ? 'y' : 'ies'}, one after another. It stops at the first verified email per job.
                </p>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-fg-subtle">
                      <th className="py-1 font-medium">Provider</th>
                      <th className="py-1 font-medium">Companies asked</th>
                      <th className="py-1 font-medium">At most</th>
                      <th className="py-1 font-medium">Left</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(preview.data?.spend ?? {}).map(([name, s]) => (
                      <tr key={name} className="border-t border-border">
                        <td className="py-1 capitalize">{name}</td>
                        <td className="py-1 tabular-nums">{s.companies}</td>
                        <td className="py-1 tabular-nums">{s.unit === 'usd' ? `$${s.worst_case.toFixed(2)}` : `${s.worst_case} ${UNIT[s.unit]}`}</td>
                        <td className={s.keys === 0 ? 'py-1 text-fg-subtle' : s.worst_case > s.remaining ? 'py-1 text-warning-fg tabular-nums' : 'py-1 tabular-nums'}>
                          {s.keys === 0 ? 'no key' : s.unit === 'usd' ? `$${s.remaining.toFixed(2)}` : `${s.remaining} ${UNIT[s.unit]}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-2xs text-fg-subtle">Upper bound: companies looked up in the last 90 days cost nothing, and most jobs stop at the first provider that finds a verified email. A provider with no credits left is skipped.</p>
              </>
            )}
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
            {running ? (
              <Button size="sm" variant="secondary" onClick={() => (stop.current = true)}>
                <Square />
                Stop after this job
              </Button>
            ) : (
              <>
                <Button size="sm" variant="ghost" onClick={close}>
                  {progress ? 'Close' : 'Cancel'}
                </Button>
                {!progress && count > 0 && (
                  <Button size="sm" variant="default" onClick={() => void start()}>
                    Search {count} job{count === 1 ? '' : 's'}
                  </Button>
                )}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
