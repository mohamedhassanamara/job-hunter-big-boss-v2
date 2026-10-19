import { ArrowLeft, CircleCheck, CircleX, LoaderCircle, MessagesSquare, RefreshCw, Sparkles, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { StageBadge, ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { ClaimCheck } from '@/components/app/verify/ClaimCheck'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { useApproveInterviewPrep, useGenerateInterviewPrep, useInterviewPrep, usePatchInterviewPrep, useVerifyInterviewPrep } from '@/lib/queries/interview'
import { useJob } from '@/lib/queries/jobs'
import type { InterviewContent, InterviewPrep, PrepSentence, StarStory, Violation } from '@/lib/types'
import { cn } from '@/lib/utils'

const LANGUAGE_LABEL = { fr: 'French', en: 'English' } as const
const PARTS = [
  ['situation', 'Situation'],
  ['task', 'Task'],
  ['action', 'Action'],
  ['result', 'Result'],
] as const

function Checks({ violations }: { violations: Violation[] }) {
  if (violations.length === 0)
    return (
      <p data-tour="interview-checks" className="flex items-center gap-2 rounded-md bg-success-bg px-3 py-2 text-sm text-success-fg">
        <CircleCheck className="size-4" />
        Every check passed: each sentence is grounded in your experience (numbers, tools and scope as written there), your years wording is exact, every story has its parts.
      </p>
    )
  return (
    <ul data-tour="interview-checks" className="space-y-1 rounded-md border border-border bg-surface px-3 py-2">
      {violations.map((v, i) => (
        <li key={i} className={cn('flex items-start gap-2 text-sm', v.severity === 'error' ? 'text-danger-fg' : 'text-warning-fg')}>
          {v.severity === 'error' ? <CircleX className="mt-0.5 size-4 shrink-0" /> : <TriangleAlert className="mt-0.5 size-4 shrink-0" />}
          <span>
            {v.where && <span className="font-medium">{v.where}: </span>}
            {v.message}
          </span>
        </li>
      ))}
    </ul>
  )
}

const areaClass = 'w-full resize-none overflow-hidden rounded-md border border-transparent bg-transparent px-2 py-1 text-sm leading-relaxed outline-none hover:border-border focus:border-primary focus:bg-surface focus:ring-3 focus:ring-ring'

function Area({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = ref.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${el.scrollHeight}px`
    }
  }, [value])
  return <textarea ref={ref} rows={1} value={value} aria-label={label} onChange={(e) => onChange(e.target.value)} className={areaClass} />
}

function Sentence({ s, sources, label, onChange }: { s: PrepSentence; sources: Record<string, string>; label: string; onChange: (s: PrepSentence) => void }) {
  return (
    <div className="space-y-0.5">
      <Area value={s.text} label={label} onChange={(text) => onChange({ ...s, text })} />
      <p className="flex flex-wrap gap-1 px-2 text-2xs text-fg-subtle">
        {s.citations.map((c) => (
          <span key={c} className="rounded-sm bg-surface-hover px-1">
            {sources[String(c)] ?? `item ${c}`}
          </span>
        ))}
      </p>
    </div>
  )
}

function Story({ n, story, sources, onChange }: { n: number; story: StarStory; sources: Record<string, string>; onChange: (s: StarStory) => void }) {
  return (
    <article className="space-y-2 rounded-lg border border-border bg-surface px-4 py-3" data-tour="interview-story">
      <header className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-fg-subtle tabular-nums">Story {n + 1}</span>
        <span className="text-sm font-medium">{story.title}</span>
        <ToneBadge tone="blue" dot={false}>
          answers: {story.requirement}
        </ToneBadge>
      </header>
      {PARTS.map(([part, label]) => (
        <div key={part} className="grid grid-cols-[72px_1fr] items-start gap-2">
          <span className="pt-1.5 text-xs font-medium text-fg-subtle">{label}</span>
          <div>
            {story[part].length === 0 ? (
              <p className="px-2 py-1 text-sm text-fg-subtle italic">{part === 'result' ? 'Your experience states no result for this: none is invented. Add what you know yourself.' : 'Nothing here.'}</p>
            ) : (
              story[part].map((s, i) => (
                <Sentence
                  key={i}
                  s={s}
                  sources={sources}
                  label={`Story ${n + 1} ${label} ${i + 1}`}
                  onChange={(next) => onChange({ ...story, [part]: story[part].map((x, j) => (j === i ? next : x)) })}
                />
              ))
            )}
          </div>
        </div>
      ))}
    </article>
  )
}

function Prep({ prep, jobId, appId }: { prep: InterviewPrep; jobId: number; appId: number }) {
  const patch = usePatchInterviewPrep()
  const approve = useApproveInterviewPrep()
  const verify = useVerifyInterviewPrep()
  const [content, setContent] = useState<InterviewContent>(prep.content)
  const saved = useRef(JSON.stringify(prep.content))
  const [saving, setSaving] = useState(false)
  const locked = prep.status !== 'draft'
  const errors = prep.violations.filter((v) => v.severity === 'error')

  useEffect(() => {
    const now = JSON.stringify(content)
    if (now === saved.current) return
    setSaving(true)
    const t = setTimeout(() => {
      patch.mutate(
        { id: prep.id, content },
        {
          onSuccess: () => ((saved.current = now), setSaving(false)),
          onError: (e) => (setSaving(false), toast.error(e.message)),
        },
      )
    }, 700)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content])

  const onApprove = () => approve.mutate(prep.id, { onSuccess: () => toast.success('Interview preparation approved'), onError: (e) => toast.error(e.message) })
  const set = (patch: Partial<InterviewContent>) => setContent((c) => ({ ...c, ...patch }))

  return (
    <div className="mx-auto w-full max-w-3xl space-y-5 px-6 py-5">
      <div className="flex flex-wrap items-center gap-2">
        <ToneBadge tone={prep.status === 'approved' ? 'green' : 'gray'}>{prep.status === 'approved' ? 'Approved' : 'Draft'} v{prep.version}</ToneBadge>
        <span className="text-xs text-fg-subtle">{saving ? 'Saving…' : 'All changes saved'}</span>
        <span className="ml-auto" data-tour="interview-approve">
          {prep.status === 'approved' ? (
            <ToneBadge tone="green" dot={false} className="h-8 px-3 text-sm">
              <CircleCheck className="size-4" />
              Approved
            </ToneBadge>
          ) : (
            <Tooltip content={errors.length ? `Fix first: ${errors[0].message}` : null}>
              <span>
                <Button variant="default" onClick={onApprove} disabled={approve.isPending || saving || errors.length > 0 || prep.verification_state === 'failed'}>
                  <CircleCheck />
                  {approve.isPending ? 'Checking claims…' : 'Approve'}
                </Button>
              </span>
            </Tooltip>
          )}
        </span>
      </div>
      <Checks violations={prep.violations} />

      <section className="space-y-1.5" data-tour="interview-pitch">
        <h2 className="text-sm font-semibold">Tell me about yourself</h2>
        <div className="rounded-lg border border-border bg-surface px-3 py-2">
          {content.pitch.map((s, i) => (
            <Sentence key={i} s={s} sources={prep.sources} label={`Pitch ${i + 1}`} onChange={(next) => set({ pitch: content.pitch.map((x, j) => (j === i ? next : x)) })} />
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold">STAR stories from your experience</h2>
        {content.stories.map((story, n) => (
          <Story key={n} n={n} story={story} sources={prep.sources} onChange={(next) => set({ stories: content.stories.map((x, j) => (j === n ? next : x)) })} />
        ))}
      </section>

      <section className="space-y-1.5" data-tour="interview-questions">
        <h2 className="text-sm font-semibold">Likely questions for this job</h2>
        <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
          {content.questions.map((q, i) => (
            <li key={i} className="px-3 py-2">
              <Area value={q.question} label={`Question ${i + 1}`} onChange={(question) => set({ questions: content.questions.map((x, j) => (j === i ? { ...x, question } : x)) })} />
              <p className="px-2 text-xs text-fg-subtle">
                checks: {q.probes}
                {q.story >= 0 && content.stories[q.story] && <> · answer with story {q.story + 1}: {content.stories[q.story].title}</>}
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-1.5">
        <h2 className="text-sm font-semibold">Questions to ask them</h2>
        <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
          {content.ask_them.map((q, i) => (
            <li key={i} className="px-3 py-1.5">
              <Area value={q} label={`Question to ask ${i + 1}`} onChange={(v) => set({ ask_them: content.ask_them.map((x, j) => (j === i ? v : x)) })} />
            </li>
          ))}
        </ul>
      </section>

      <ClaimCheck
        verification={prep.verification}
        state={prep.verification_state}
        gate="approval"
        verifying={verify.isPending}
        onVerify={!locked && errors.length === 0 && !saving ? () => verify.mutate(prep.id, { onError: (e) => toast.error(e.message) }) : undefined}
      />
      <p className="text-xs text-fg-subtle">
        <Link to={`/jobs/${jobId}`} className="underline-offset-2 hover:underline">
          Back to the job
        </Link>{' '}
        · application {appId}
      </p>
    </div>
  )
}

export default function InterviewPrepPage() {
  const { id } = useParams()
  const jobId = Number(id)
  const job = useJob(jobId)
  const appId = job.data?.application.id ?? NaN
  const studio = useInterviewPrep(appId)
  const generate = useGenerateInterviewPrep()
  const [language, setLanguage] = useState<string | null>(null)
  const s = studio.data
  const lang = language ?? s?.language ?? 'en'
  const loading = job.isPending || (Number.isFinite(appId) && studio.isPending)
  const error = job.error ?? studio.error
  const run = () => generate.mutate({ appId, language: lang }, { onSuccess: () => toast.success('Interview preparation written'), onError: (e) => toast.error(e.message) })
  const picker = (
    <span data-tour="interview-language">
      <Select aria-label="Language" value={lang} onValueChange={setLanguage} options={[{ value: 'en', label: 'English' }, { value: 'fr', label: 'French' }]} className="w-32" />
    </span>
  )

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-bg px-5">
        <Tooltip content="Back to job">
          <Button size="icon" variant="ghost" asChild>
            <Link to={`/jobs/${jobId}`} aria-label="Back to job">
              <ArrowLeft />
            </Link>
          </Button>
        </Tooltip>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">
            Interview prep{job.data && <span className="font-normal text-fg-muted"> · {job.data.title}</span>}
          </p>
          <p className="truncate text-xs text-fg-subtle">{job.data ? `${job.data.company.name} · stories and a pitch from your experience only, every claim checked` : ' '}</p>
        </div>
        {job.data && <StageBadge stage={job.data.application.stage} label={job.data.application.stage_label} />}
        {s?.prep && (
          <>
            {picker}
            <Button onClick={run} disabled={generate.isPending}>
              <RefreshCw className={generate.isPending ? 'animate-spin' : undefined} />
              {generate.isPending ? 'Writing…' : 'Regenerate'}
            </Button>
          </>
        )}
        <TourButton tour="interview" />
      </div>
      <div className="relative min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <div className="mx-auto max-w-3xl space-y-3 p-6">
            <Skeleton className="h-10" />
            <Skeleton className="h-32" />
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={() => (job.error ? job.refetch() : studio.refetch())} />
        ) : !s?.prep ? (
          <EmptyState
            icon={MessagesSquare}
            title={generate.isPending ? 'Writing your interview preparation…' : 'No interview preparation for this job yet'}
            description={
              s?.has_experience
                ? `A pitch, 3-4 STAR stories, likely questions and questions to ask, in ${LANGUAGE_LABEL[lang as 'fr' | 'en']}. Every sentence about you comes from your Experience and is checked; a story whose experience states no result has none, never an invented one.`
                : 'The stories come only from your Experience. Add your roles and projects first.'
            }
            action={
              <div className="flex justify-center gap-2">
                {s?.has_experience ? (
                  <Button variant="default" onClick={run} disabled={generate.isPending}>
                    <Sparkles />
                    Write interview prep
                  </Button>
                ) : (
                  <Button variant="default" asChild>
                    <Link to="/experience">Open Experience</Link>
                  </Button>
                )}
                {picker}
                <TourButton tour="interview" />
              </div>
            }
          />
        ) : (
          <Prep key={s.prep.id} prep={s.prep} jobId={jobId} appId={appId} />
        )}
        {generate.isPending && s?.prep && (
          <div className="absolute inset-0 flex items-center justify-center bg-bg/60">
            <span className="inline-flex items-center gap-2 rounded-md bg-surface px-3 py-2 text-sm shadow-sm">
              <LoaderCircle className="size-4 animate-spin text-primary" />
              Writing…
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
