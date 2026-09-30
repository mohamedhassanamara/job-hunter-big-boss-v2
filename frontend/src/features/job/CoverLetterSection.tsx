import { ArrowRight, FileText, Lock, Sparkles } from 'lucide-react'
import { Link } from 'react-router'
import { ToneBadge } from '@/components/app/badges'
import { Section } from '@/components/app/PageHeader'
import { EmptyState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { relativeTime } from '@/lib/format'
import { useLetterStudio } from '@/lib/queries/letters'
import type { JobDetail } from '@/lib/types'

const LANGUAGE = { fr: 'French', en: 'English' } as const

/** Web apply: the cover letter's versions, and the way into the Cover letter studio. */
export function CoverLetterSection({ job }: { job: JobDetail }) {
  const app = job.application
  const hasApprovedCv = job.cv_versions.some((v) => v.status === 'approved')
  const show = app.stage !== 'new' && app.stage !== 'closed' && app.tracks.application !== 'applied' && (hasApprovedCv || job.cv_versions.length > 0)
  const { data, isPending } = useLetterStudio(show ? app.id : NaN)
  if (!show) return null
  const letters = data?.letters ?? []
  return (
    <Section
      title="Cover letter"
      action={
        letters.length > 0 && (
          <Button size="xs" variant="ghost" asChild>
            <Link to={`/jobs/${job.id}/letter`}>
              Open studio
              <ArrowRight />
            </Link>
          </Button>
        )
      }
    >
      <div data-tour="job-letter">
        {isPending ? (
          <Skeleton className="m-4 h-10" />
        ) : letters.length === 0 ? (
          <EmptyState
            compact
            icon={FileText}
            title="No cover letter yet"
            description={
              hasApprovedCv
                ? `One page in ${LANGUAGE[data?.language ?? 'en']} (the listing's language), from your approved CV. Optional: send it only where the form asks for one.`
                : 'Approve the CV first: the letter is written from it.'
            }
            action={
              <div className="flex gap-2">
                {hasApprovedCv && (
                  <Button size="sm" asChild>
                    <Link to={`/jobs/${job.id}/letter`}>
                      <Sparkles />
                      Write cover letter
                    </Link>
                  </Button>
                )}
                <TourButton tour="letter" />
              </div>
            }
          />
        ) : (
          <ul>
            {letters.slice(0, 3).map((l) => (
              <li key={l.id} className="flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0">
                <FileText className="size-4 text-fg-subtle" />
                <span className="text-sm font-medium">v{l.version}</span>
                <ToneBadge tone={l.status === 'approved' ? 'green' : l.status === 'draft' ? 'amber' : 'gray'}>
                  {l.status === 'approved' ? 'Approved' : l.status === 'draft' ? 'Needs review' : 'Superseded'}
                </ToneBadge>
                {l.locked_at && (
                  <ToneBadge tone="blue">
                    <Lock className="size-3" />
                    Sent
                  </ToneBadge>
                )}
                <span className="text-xs text-fg-subtle">
                  {LANGUAGE[l.language]} · {l.word_count} words
                </span>
                <span className="ml-auto text-xs text-fg-subtle">{relativeTime(l.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  )
}
