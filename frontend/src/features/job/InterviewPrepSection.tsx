import { ArrowRight, MessagesSquare } from 'lucide-react'
import { Link } from 'react-router'
import { ToneBadge } from '@/components/app/badges'
import { Section } from '@/components/app/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { relativeTime } from '@/lib/format'
import { useInterviewPrep } from '@/lib/queries/interview'
import type { JobDetail } from '@/lib/types'

/** STAR stories and a pitch for this job, from your experience only: the way into the page. */
export function InterviewPrepSection({ job }: { job: JobDetail }) {
  const app = job.application
  const show = app.stage !== 'new' && app.stage !== 'closed'
  const { data, isPending } = useInterviewPrep(show ? app.id : NaN)
  if (!show) return null
  const prep = data?.prep
  return (
    <Section
      title="Interview prep"
      action={
        <Button size="xs" variant={prep ? 'ghost' : 'outline'} asChild>
          <Link to={`/jobs/${job.id}/interview`}>
            {prep ? 'Open' : 'Prepare'}
            <ArrowRight />
          </Link>
        </Button>
      }
    >
      <div data-tour="job-interview" className="px-4 py-3 text-sm">
        {isPending ? (
          <Skeleton className="h-8" />
        ) : prep ? (
          <p className="flex flex-wrap items-center gap-2">
            <MessagesSquare className="size-4 text-fg-subtle" />
            {prep.content.stories.length} STAR stories · {prep.content.questions.length} likely questions
            <ToneBadge tone={prep.status === 'approved' ? 'green' : 'gray'}>{prep.status === 'approved' ? 'Approved' : 'Draft'} v{prep.version}</ToneBadge>
            <span className="text-xs text-fg-subtle">{relativeTime(prep.created_at)}</span>
          </p>
        ) : (
          <p className="text-fg-muted">A pitch, STAR stories and likely questions for this job, built only from your experience.</p>
        )}
      </div>
    </Section>
  )
}
