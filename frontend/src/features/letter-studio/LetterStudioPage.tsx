import { ArrowLeft, CircleCheck, Copy, Download, FileText, LoaderCircle, Lock, RefreshCw, Sparkles } from 'lucide-react'
import { useCallback, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { StageBadge, ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { apiUrl } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import { useJob } from '@/lib/queries/jobs'
import { useApproveLetter, useGenerateLetter, useLetterStudio, useSetLetterLanguage } from '@/lib/queries/letters'
import type { CoverLetter } from '@/lib/types'
import { LetterEditor } from './LetterEditor'

const STATUS_LABEL = { draft: 'Draft', approved: 'Approved', superseded: 'Superseded' } as const
const LANGUAGE_LABEL = { fr: 'French', en: 'English' } as const

function PageBadge({ letter }: { letter: CoverLetter }) {
  if (letter.error) return <ToneBadge tone="red">LaTeX error</ToneBadge>
  if (letter.page_count == null) return <ToneBadge tone="gray">Not compiled</ToneBadge>
  return (
    <ToneBadge tone={letter.page_count === 1 ? 'green' : 'red'}>
      {letter.page_count} page{letter.page_count === 1 ? '' : 's'} · {letter.word_count} words
    </ToneBadge>
  )
}

export default function LetterStudioPage() {
  const { id } = useParams()
  const jobId = Number(id)
  const navigate = useNavigate()
  const job = useJob(jobId)
  const appId = job.data?.application.id ?? NaN
  const studio = useLetterStudio(appId)
  const generate = useGenerateLetter()
  const approve = useApproveLetter()
  const setLanguage = useSetLetterLanguage()
  const [selected, setSelected] = useState<number | null>(null)

  const letters = studio.data?.letters ?? []
  const letter = letters.find((l) => l.id === selected) ?? letters.find((l) => l.status !== 'superseded') ?? letters[0]
  const noCv = studio.data && studio.data.approved_cv_id == null
  const blocked = !!noCv || studio.data?.template_ok === false

  const runGenerate = useCallback(() => {
    if (!Number.isFinite(appId)) return
    const t = toast.loading('Writing your cover letter with Claude…', { description: 'Usually under a minute. Every sentence is then checked against your CV and the listing.' })
    generate.mutate(
      { appId },
      {
        onSuccess: (l) => {
          setSelected(l.id)
          const errors = l.violations.filter((v) => v.severity === 'error').length
          toast[errors ? 'warning' : 'success'](`Cover letter v${l.version} ready for review`, {
            id: t,
            description: `${LANGUAGE_LABEL[l.language]} · ${l.word_count} words${errors ? ` · ${errors} problem${errors > 1 ? 's' : ''} to fix` : ' · every check passed'}`,
          })
        },
        onError: (e) => toast.error(e.message, { id: t }),
      },
    )
  }, [appId, generate])

  const onApprove = () => {
    if (!letter) return
    approve.mutate(letter.id, {
      onSuccess: (l) =>
        toast.success(`Cover letter v${l.version} approved`, {
          description: 'It goes with your CV when you apply.',
          duration: 10000,
          action: { label: 'Go to Ready to apply', onClick: () => navigate('/applications?tab=ready') },
        }),
      onError: (e) => toast.error(e.message),
    })
  }

  const copyText = () => {
    if (!letter) return
    navigator.clipboard.writeText(letter.text).then(
      () => toast.success('Cover letter copied as text', { description: 'Paste it into the application form.' }),
      () => toast.error("Couldn't copy to the clipboard"),
    )
  }

  const error = job.error ?? studio.error
  const loading = job.isPending || (Number.isFinite(appId) && studio.isPending)
  const errors = letter?.violations.filter((v) => v.severity === 'error') ?? []
  const s = studio.data

  const languagePicker = s && (
    <span data-tour="letter-language">
      <Select
        aria-label="Letter language"
        size="sm"
        value={s.language_setting}
        onValueChange={(language) =>
          setLanguage.mutate(
            { appId, language },
            { onSuccess: (r) => toast.success(`Next letter: ${LANGUAGE_LABEL[r.language]}`, { description: 'Regenerate to write it in that language.' }), onError: (e) => toast.error(e.message) },
          )
        }
        options={[
          { value: 'auto', label: `Listing's language (${LANGUAGE_LABEL[s.detected_language]})` },
          { value: 'fr', label: 'French' },
          { value: 'en', label: 'English' },
        ]}
        className="w-56"
      />
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
            Cover letter{job.data && <span className="font-normal text-fg-muted"> · {job.data.title}</span>}
          </p>
          <p className="truncate text-xs text-fg-subtle">{job.data ? `${job.data.company.name} · one page, facts from your approved CV only` : ' '}</p>
        </div>
        {job.data && <StageBadge stage={job.data.application.stage} label={job.data.application.stage_label} />}
        {letter && (
          <>
            <PageBadge letter={letter} />
            <span data-tour="letter-versions">
              <Select
                aria-label="Version"
                value={String(letter.id)}
                onValueChange={(v) => setSelected(Number(v))}
                options={letters.map((l) => ({ value: String(l.id), label: `v${l.version} · ${STATUS_LABEL[l.status]}${l.locked_at ? ' · sent' : ''} · ${relativeTime(l.created_at)}` }))}
                className="w-56"
              />
            </span>
            <Button onClick={runGenerate} disabled={generate.isPending || blocked}>
              <RefreshCw className={generate.isPending ? 'animate-spin' : undefined} />
              {generate.isPending ? 'Writing…' : 'Regenerate'}
            </Button>
            <Tooltip content="Copy as text (for the application form)">
              <Button variant="ghost" size="icon" onClick={copyText} aria-label="Copy as text">
                <Copy />
              </Button>
            </Tooltip>
            <Tooltip content={letter.download_name}>
              <Button variant="ghost" size="icon" asChild disabled={!letter.has_pdf}>
                <a href={apiUrl(`/letters/${letter.id}/pdf`, { download: true, v: letter.updated_at })} aria-label="Download PDF">
                  <Download />
                </a>
              </Button>
            </Tooltip>
            <span data-tour="letter-approve">
              {letter.locked_at ? (
                <ToneBadge tone="gray" dot={false} className="h-8 px-3 text-sm">
                  <Lock className="size-4" />
                  Sent
                </ToneBadge>
              ) : letter.status === 'approved' ? (
                <ToneBadge tone="green" dot={false} className="h-8 px-3 text-sm">
                  <CircleCheck className="size-4" />
                  Approved
                </ToneBadge>
              ) : (
                <Tooltip content={errors.length ? `Fix first: ${errors[0].message}` : null}>
                  <span>
                    <Button variant="default" onClick={onApprove} disabled={approve.isPending || letter.status !== 'draft' || errors.length > 0 || !letter.has_pdf}>
                      <CircleCheck />
                      Approve
                    </Button>
                  </span>
                </Tooltip>
              )}
            </span>
          </>
        )}
      </div>

      {loading ? (
        <div className="grid flex-1 grid-cols-2 gap-6 p-6">
          <div className="space-y-3">
            <Skeleton className="h-10" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
          <Skeleton className="aspect-[1/1.294] w-full max-w-[620px]" />
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={() => (job.error ? job.refetch() : studio.refetch())} />
      ) : !letter ? (
        <EmptyState
          icon={FileText}
          title={generate.isPending ? 'Writing your cover letter…' : 'No cover letter for this job yet'}
          description={
            noCv
              ? 'The letter is written from your approved CV. Approve the CV for this job first.'
              : s?.template_ok === false
                ? "The CV template has no cover letter layout (cover_letter.tex.j2). Pick a template that has one."
                : `One page in ${LANGUAGE_LABEL[s?.language ?? 'en']}, written from your approved CV v${s?.approved_cv_version ?? ''} and the listing. Every sentence is checked; nothing is invented.`
          }
          action={
            <div className="flex gap-2">
              {noCv ? (
                <Button variant="default" asChild>
                  <Link to={`/jobs/${jobId}/cv`}>Open CV Studio</Link>
                </Button>
              ) : (
                <Button variant="default" onClick={runGenerate} disabled={generate.isPending || blocked}>
                  <Sparkles />
                  Write cover letter
                </Button>
              )}
              {languagePicker}
              <TourButton tour="letter" />
            </div>
          }
        />
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] max-xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="min-h-0 overflow-y-auto border-r border-border bg-bg">
            <div className="sticky top-0 z-10 flex h-11 items-center justify-between gap-3 border-b border-border bg-bg px-5 text-xs">
              <span className="font-medium text-fg-muted">Language of the next letter</span>
              {languagePicker}
            </div>
            <LetterEditor key={letter.id} letter={letter} onNewVersion={setSelected} />
          </div>
          <div data-tour="letter-preview" className="relative min-h-0 bg-bg-subtle">
            {letter.error ? (
              <div className="p-6">
                <ErrorState error={new Error(letter.error.split('\n')[0])} />
              </div>
            ) : (
              <iframe
                key={`${letter.id}-${letter.updated_at}`}
                title="Cover letter preview"
                src={`${apiUrl(`/letters/${letter.id}/pdf`, { v: letter.updated_at })}#view=FitH&toolbar=0`}
                className="h-full w-full border-0"
              />
            )}
            {generate.isPending && (
              <div className="absolute inset-0 flex items-center justify-center bg-bg/60">
                <span className="inline-flex items-center gap-2 rounded-md bg-surface px-3 py-2 text-sm shadow-sm">
                  <LoaderCircle className="size-4 animate-spin text-primary" />
                  Writing…
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
