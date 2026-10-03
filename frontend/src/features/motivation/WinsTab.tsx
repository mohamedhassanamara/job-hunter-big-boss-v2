import { BriefcaseBusiness, CalendarCheck, Flame, HeartHandshake, MessageSquareReply, Package, Sprout, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ErrorState, SkeletonRows } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { usePendingDelete } from '@/hooks/usePendingDelete'
import { relativeTime } from '@/lib/format'
import { useAddWin, useDeleteWin, useWins } from '@/lib/queries/motivation'

function Stat({ icon: Icon, label, value, hint }: { icon: typeof Flame; label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <p className="flex items-center gap-1.5 text-xs text-fg-subtle">
        <Icon className="size-3.5" />
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="text-xs text-fg-muted">{hint}</p>}
    </div>
  )
}

/** Your progress from real data, plus a small journal of wins. */
export function WinsTab() {
  const wins = useWins()
  const add = useAddWin()
  const del = useDeleteWin()
  const pending = usePendingDelete((id) => del.mutate(id))
  const [text, setText] = useState('')

  if (wins.error) return <ErrorState error={wins.error} onRetry={() => wins.refetch()} />
  const w = wins.data
  const journal = (w?.journal ?? []).filter((j) => !pending.hidden.has(j.id))

  return (
    <div className="mx-auto max-w-5xl space-y-6 py-6" data-tour="motiv-wins">
      {w?.recent_rejection && (
        <div className="flex gap-3 rounded-lg border border-tone-teal-border bg-tone-teal-bg px-4 py-3 text-sm text-tone-teal-fg">
          <Sprout className="mt-0.5 size-4 shrink-0" />
          <p>
            A rejection stings, and it says little about you. Cold applications and outreach get low response rates for everyone; what moves the needle is volume and consistency over weeks, not any single result. Keep the streak going.
          </p>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {!w ? (
          Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-24" />)
        ) : (
          <>
            <Stat icon={CalendarCheck} label="Applications this week" value={w.applications_week} />
            <Stat icon={BriefcaseBusiness} label="Applications in total" value={w.applications_total} />
            <Stat icon={MessageSquareReply} label="Replies" value={w.replies} hint={w.positive_replies ? `${w.positive_replies} positive` : undefined} />
            <Stat icon={HeartHandshake} label="Interviews" value={w.interviews} />
            <Stat icon={Flame} label="Longest streak" value={w.longest_streak} hint="days in a row" />
            <Stat icon={Package} label="Chests opened" value={w.chests_opened} />
          </>
        )}
      </div>
      <div className="space-y-3">
        <div className="space-y-1">
          <h2 className="text-base font-semibold">Wins journal</h2>
          <p className="text-sm text-fg-muted">Write down the small things too: a good CV, a kind reply, a hard email sent.</p>
        </div>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate(text, { onSuccess: () => (setText(''), toast.success('Win saved')), onError: (err) => toast.error(err.message) })
          }}
        >
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Today's win…" aria-label="A win" className="max-w-xl" />
          <Button type="submit" variant="default" disabled={!text.trim() || add.isPending}>
            Add
          </Button>
        </form>
        {!w ? (
          <SkeletonRows rows={3} />
        ) : journal.length === 0 ? (
          <p className="text-sm text-fg-muted">Your first win goes here.</p>
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
            {journal.map((j) => (
              <li key={j.id} className="group flex items-center gap-3 px-4 py-2.5">
                <span className="flex-1 text-sm">{j.text}</span>
                <span className="text-xs whitespace-nowrap text-fg-subtle">{relativeTime(j.created_at)}</span>
                <Button size="icon-sm" variant="ghost" aria-label="Delete this win" className="opacity-0 group-focus-within:opacity-100 group-hover:opacity-100" onClick={() => pending.remove(j.id, 'Win')}>
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
