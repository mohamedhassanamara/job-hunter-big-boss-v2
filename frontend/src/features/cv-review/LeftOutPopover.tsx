import { Layers } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { useCVLeftOut, usePatchCV } from '@/lib/queries/workflow'
import type { CVReviewRow } from '@/lib/types'

/** The bullets and projects of your experience this CV leaves out, with the relevance the model gave
 * each for this job. A toggle forces one in (or out again): the CV is re-fitted and the same checks
 * run, with no model call (CV Studio's force in/out). */
export function LeftOutPopover({ row }: { row: CVReviewRow }) {
  const [open, setOpen] = useState(false)
  const { data, isPending, error } = useCVLeftOut(row.cv_id, open)
  const patch = usePatchCV()

  const toggle = (key: string, on: boolean) => {
    if (!data) return
    const force_in = on ? [...data.force_in, key] : data.force_in.filter((k) => k !== key)
    patch.mutate(
      { id: row.cv_id, force_in },
      { onError: (e) => toast.error(e.message) },
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-tour="review-cvs-left-out"
          className="inline-flex items-center gap-1 rounded text-2xs text-fg-muted underline-offset-2 hover:text-fg hover:underline"
        >
          <Layers className="size-3" />
          Left out ({row.left_out_count})
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[420px] max-w-[90vw] space-y-2 p-0" align="start">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <p className="text-sm font-medium">Left out of this CV</p>
          <p className="text-2xs text-fg-subtle tabular-nums">
            {data?.fill != null ? `${Math.round(data.fill * 100)}% full` : ''}
            {data?.page_count && data.page_count !== 1 ? ` · ${data.page_count} pages` : ''}
          </p>
        </div>
        <div className="max-h-80 overflow-y-auto px-3 pb-3">
          {isPending ? (
            <Skeleton className="h-24" />
          ) : error ? (
            <p className="text-xs text-danger-fg">{error.message}</p>
          ) : data.items.length === 0 ? (
            <p className="py-2 text-xs text-fg-muted">Everything in your experience that matches this job is on the CV.</p>
          ) : (
            <ul className="divide-y divide-border">
              {data.items.map((x) => (
                <li key={x.key} className="flex items-start gap-3 py-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium">
                      {x.kind === 'project' ? 'Project: ' : ''}
                      {x.title}
                      {x.org ? <span className="font-normal text-fg-subtle"> · {x.org}</span> : null}
                    </p>
                    {x.text && <p className="text-xs text-fg-muted">{x.text}</p>}
                    <p className="mt-0.5 text-2xs text-fg-subtle">
                      Relevance {x.relevance ?? 'not rated'}
                      {x.relevance != null ? '/10' : ''} · {x.why}
                    </p>
                  </div>
                  <Switch
                    checked={x.included}
                    disabled={patch.isPending}
                    onCheckedChange={(on) => toggle(x.key, on)}
                    aria-label={`${x.included ? 'Remove' : 'Include'} ${x.text ?? x.title}`}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
