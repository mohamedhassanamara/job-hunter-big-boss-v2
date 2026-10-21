import { ArrowLeft, CircleCheck, Copy, Download, FileText, LoaderCircle, Lock, RefreshCw, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { StageBadge, ToneBadge } from '@/components/app/badges'
import { RegenerateDialog } from '@/components/app/RegenerateDialog'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip } from '@/components/ui/tooltip'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { apiUrl } from '@/lib/api'
import { relativeTime } from '@/lib/format'
import { useJob } from '@/lib/queries/jobs'
import { useApproveLetter, useGenerateLetter, useLetterStudio, useSetLetterLanguage } from '@/lib/queries/letters'
import type { CoverLetter, LetterFormat } from '@/lib/types'
import { FormPreview, FormQuestion } from './FormText'
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
  const url = useSearchParamState()
  const format: LetterFormat = url.get('format') === 'form' ? 'form' : 'pdf'
  const form = format === 'form'
  const [ask, setAsk] = useState<{ question?: string; limit?: string }>({})

  const all = studio.data?.letters ?? []
  const letters = all.filter((l) => (l.format ?? 'pdf') === format)
  const letter = letters.find((l) => l.id === selected) ?? letters.find((l) => l.status !== 'superseded') ?? letters[0]
  const noCv = studio.data && studio.data.approved_cv_id == null
  const blocked = !!noCv || (!form && studio.data?.template_ok === false)
  const question = ask.question ?? letter?.question ?? ''
  const limit = ask.limit ?? (letter?.char_limit != null ? String(letter.char_limit) : '')

  const [regenOpen, setRegenOpen] = useState(false)
  const runGenerate = (feedback = '') => {
    if (!Number.isFinite(appId)) return
    if (form && !question.trim()) {
      toast.error("Paste the form's question first")
      return
    }
    const t = toast.loading(`Writing your ${form ? 'form text' : 'cover letter'} with Claude…`, { description: 'Usually under a minute. Every sentence is then checked against your CV and the listing.' })
    generate.mutate(
      { appId, format, question: form ? question.trim() : undefined, char_limit: form && limit ? Number(limit) : undefined, feedback },
      {
        onSuccess: (l) => {
          setSelected(l.id)
          const errors = l.violations.filter((v) => v.severity === 'error').length
          toast[errors ? 'warning' : 'success'](`${l.format === 'form' ? 'Form text' : 'Cover letter'} v${l.version} ready for review`, {
            id: t,
            description: `${LANGUAGE_LABEL[l.language]} · ${l.word_count} words${errors ? ` · ${errors} problem${errors > 1 ? 's' : ''} to fix` : ' · every check passed'}`,
          })
        },
        onError: (e) => toast.error(e.message, { id: t }),
      },
    )
  }

  const onApprove = () => {
    if (!letter) return
    approve.mutate(letter.id, {
      onSuccess: (l) =>
        toast.success(`${l.format === 'form' ? 'Form text' : 'Cover letter'} v${l.version} approved`, {
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
          <p className="truncate text-xs text-fg-subtle">{job.data ? `${job.data.company.name} · ${form ? "text for the form's box" : 'one page'}, facts from your approved CV only` : ' '}</p>
        </div>
        <Tabs value={format} onValueChange={(v) => (setSelected(null), url.set({ format: v === 'form' ? 'form' : null }))}>
          <TabsList data-tour="letter-format">
            <TabsTrigger value="pdf" count={all.filter((l) => (l.format ?? 'pdf') === 'pdf').length}>
              PDF letter
            </TabsTrigger>
            <TabsTrigger value="form" count={all.filter((l) => l.format === 'form').length}>
              Form text
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {job.data && <StageBadge stage={job.data.application.stage} label={job.data.application.stage_label} />}
        {letter && (
          <>
            {form ? (
              <ToneBadge tone={letter.char_limit != null && letter.length > letter.char_limit ? 'red' : 'green'}>
                {letter.char_limit != null ? `${letter.length}/${letter.char_limit} chars` : `${letter.length} chars`} · {letter.word_count} words
              </ToneBadge>
            ) : (
              <PageBadge letter={letter} />
            )}
            <span data-tour="letter-versions">
              <Select
                aria-label="Version"
                value={String(letter.id)}
                onValueChange={(v) => setSelected(Number(v))}
                options={letters.map((l) => ({ value: String(l.id), label: `v${l.version} · ${STATUS_LABEL[l.status]}${l.locked_at ? ' · sent' : ''} · ${relativeTime(l.created_at)}${l.feedback ? ` · “${l.feedback.slice(0, 40)}”` : ''}` }))}
                className="w-72"
              />
            </span>
            <Button onClick={() => setRegenOpen(true)} disabled={generate.isPending || blocked}>
              <RefreshCw className={generate.isPending ? 'animate-spin' : undefined} />
              {generate.isPending ? 'Writing…' : 'Regenerate'}
            </Button>
            <Tooltip content="Copy as text (for the application form)">
              <Button variant="ghost" size="icon" onClick={copyText} aria-label="Copy as text">
                <Copy />
              </Button>
            </Tooltip>
            {!form && <Tooltip content={letter.download_name}>
              <Button variant="ghost" size="icon" asChild disabled={!letter.has_pdf}>
                <a href={apiUrl(`/letters/${letter.id}/pdf`, { download: true, v: letter.updated_at })} aria-label="Download PDF">
                  <Download />
                </a>
              </Button>
            </Tooltip>}
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
                    <Button variant="default" onClick={onApprove} disabled={approve.isPending || letter.status !== 'draft' || errors.length > 0 || letter.verification_state === 'failed' || (!form && !letter.has_pdf)}>
                      <CircleCheck />
                      {approve.isPending ? 'Checking claims…' : 'Approve'}
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
          title={generate.isPending ? `Writing your ${form ? 'form text' : 'cover letter'}…` : form ? 'No form text yet' : 'No cover letter for this job yet'}
          description={
            noCv
              ? 'The letter is written from your approved CV. Approve the CV for this job first.'
              : form
                ? `For a text box like “Expliquez-nous pourquoi vous souhaitez nous rejoindre”: paste the question (and the box's character limit). Plain text in ${LANGUAGE_LABEL[s?.language ?? 'en']}, answering it directly: no header, date, subject line or closing formula.`
                : s?.template_ok === false
                ? "The CV template has no cover letter layout (cover_letter.tex.j2). Pick a template that has one."
                : `One page in ${LANGUAGE_LABEL[s?.language ?? 'en']}, written from your approved CV v${s?.approved_cv_version ?? ''} and the listing. Every sentence is checked; nothing is invented.`
          }
          action={
            <div className="w-full max-w-xl space-y-3">
              {form && !noCv && <FormQuestion question={question} limit={limit} onChange={(n) => setAsk({ ...ask, ...n })} />}
            <div className="flex justify-center gap-2">
              {noCv ? (
                <Button variant="default" asChild>
                  <Link to={`/jobs/${jobId}/cv`}>Open CV Studio</Link>
                </Button>
              ) : (
                <Button variant="default" onClick={() => runGenerate()} disabled={generate.isPending || blocked}>
                  <Sparkles />
                  {form ? 'Write form text' : 'Write cover letter'}
                </Button>
              )}
              {languagePicker}
              <TourButton tour="letter" />
            </div>
            </div>
          }
        />
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] max-xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="min-h-0 overflow-y-auto border-r border-border bg-bg">
            <div className="sticky top-0 z-10 flex h-11 items-center justify-between gap-3 border-b border-border bg-bg px-5 text-xs">
              <span className="font-medium text-fg-muted">Language of the next {form ? 'text' : 'letter'}</span>
              {languagePicker}
            </div>
            {form && (
              <div className="border-b border-border px-5 py-4">
                <FormQuestion question={question} limit={limit} onChange={(n) => setAsk({ ...ask, ...n })} />
                <p className="mt-2 text-xs text-fg-subtle">Changed the question or the limit? Regenerate to answer it again.</p>
              </div>
            )}
            <LetterEditor key={letter.id} letter={letter} onNewVersion={setSelected} approving={approve.isPending} />
          </div>
          <div data-tour="letter-preview" className="relative min-h-0 bg-bg-subtle">
            {form ? (
              <FormPreview letter={letter} />
            ) : letter.error ? (
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
      <RegenerateDialog
        open={regenOpen}
        onClose={() => setRegenOpen(false)}
        title={form ? 'Regenerate the form text' : 'Regenerate the cover letter'}
        hint="Claude edits the latest version toward your feedback instead of starting over. Every sentence is checked again, and every version is kept in the version list so you can go back."
        pending={generate.isPending}
        onSubmit={(feedback) => {
          setRegenOpen(false)
          runGenerate(feedback)
        }}
      />
    </div>
  )
}
