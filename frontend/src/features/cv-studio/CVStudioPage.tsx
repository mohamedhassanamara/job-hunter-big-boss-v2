import { ArrowLeft, CircleCheck, Download, FileText, LoaderCircle, RefreshCw, Sparkles } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { StageBadge, ToneBadge } from '@/components/app/badges'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { apiUrl } from '@/lib/api'
import { keys } from '@/lib/queries/keys'
import { relativeTime } from '@/lib/format'
import { useJob } from '@/lib/queries/jobs'
import { useApproveCV, useCVStudio, useGenerateCV, useGenerateDraft, usePatchCV } from '@/lib/queries/workflow'
import type { CVPatchInput, CVStudio, CVVersion } from '@/lib/types'
import { CVContentPanel } from './CVContentPanel'

const STATUS_LABEL = { draft: 'Draft', approved: 'Approved', superseded: 'Superseded' } as const

function FitBadge({ version }: { version: CVVersion }) {
  if (version.error) return <ToneBadge tone="red">LaTeX error</ToneBadge>
  if (version.page_count == null) return <ToneBadge tone="gray">Not compiled</ToneBadge>
  const pct = version.fill != null ? Math.round(version.fill * 100) : null
  const ok = version.page_count === 1
  return (
    <Tooltip content={`${version.fit_passes} fit pass${version.fit_passes === 1 ? '' : 'es'} · template ${version.template}${version.duration_ms ? ` · ${Math.round(version.duration_ms / 1000)}s` : ''}`}>
      <span>
        <ToneBadge tone={ok ? 'green' : 'red'}>
          {version.page_count} page{version.page_count === 1 ? '' : 's'}
          {pct != null && ok ? ` · ${pct}% full` : ''}
        </ToneBadge>
      </span>
    </Tooltip>
  )
}

function Workspace({ studio, version }: { studio: CVStudio; version: CVVersion }) {
  const patch = usePatchCV()
  const qc = useQueryClient()
  const readOnly = version.status === 'superseded'
  const onPatch = (body: CVPatchInput) =>
    patch.mutate(
      { id: version.id, ...body },
      {
        onSuccess: (v) => {
          if (v.id !== version.id) toast.success(`Changes saved as a new draft (v${v.version})`)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  return (
    <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] max-xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
      <div data-tour="cv-editor" className="min-h-0 overflow-y-auto border-r border-border bg-bg">
        <div className="sticky top-0 z-10 flex h-10 items-center justify-between border-b border-border bg-bg px-5 text-xs">
          <span className="font-medium text-fg-muted">From your experience pool</span>
          <span className="text-fg-subtle">
            {patch.isPending ? 'Re-fitting the page…' : readOnly ? 'Superseded, read only' : version.status === 'approved' ? 'Changes create a new draft' : 'Toggle or edit: the page re-fits'}
          </span>
        </div>
        {studio.usage ? (
          <CVContentPanel version={version} usage={studio.usage} readiness={studio.readiness} readOnly={readOnly} busy={patch.isPending} onPatch={onPatch} />
        ) : (
          <p className="px-5 py-4 text-sm text-fg-muted">This version has no generator plan. Regenerate to edit it.</p>
        )}
      </div>
      <div data-tour="cv-preview" className="relative min-h-0 bg-bg-subtle">
        {version.error ? (
          <div className="p-6">
            <ErrorState error={new Error(version.error.split('\n')[0])} />
            <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-surface p-3 text-2xs text-fg-muted">{version.error}</pre>
          </div>
        ) : (
          <iframe
            key={`${version.id}-${version.updated_at}`}
            title="CV preview"
            // A version without a PDF (sample data) is compiled on first view: refresh its badge.
            onLoad={() => version.page_count == null && void qc.invalidateQueries({ queryKey: keys.cv(version.application_id) })}
            src={`${apiUrl(`/cv/${version.id}/pdf`, { v: version.updated_at })}#view=FitH&toolbar=0`}
            className="h-full w-full border-0"
          />
        )}
        {patch.isPending && (
          <div className="absolute inset-0 flex items-center justify-center bg-bg/60">
            <span className="inline-flex items-center gap-2 rounded-md bg-surface px-3 py-2 text-sm shadow-sm">
              <LoaderCircle className="size-4 animate-spin text-primary" />
              Recompiling…
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function CVStudioPage() {
  const { id } = useParams()
  const jobId = Number(id)
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const job = useJob(jobId)
  const appId = job.data?.application.id ?? NaN
  const studio = useCVStudio(appId)
  const generate = useGenerateCV()
  const patch = usePatchCV()
  const approve = useApproveCV()
  const generateDraft = useGenerateDraft()
  const [selected, setSelected] = useState<number | null>(null)
  const autoGenerated = useRef(false)

  const versions = studio.data?.versions ?? []
  const version = versions.find((v) => v.id === selected) ?? versions.find((v) => v.status !== 'superseded') ?? versions[0]
  const templates = (studio.data?.templates ?? []).filter((t) => t.valid)
  const blockers = (studio.data?.readiness ?? []).filter((r) => r.severity === 'blocker')

  const runGenerate = useCallback(() => {
    if (!Number.isFinite(appId)) return
    const t = toast.loading('Tailoring your CV with Claude…', { description: 'Usually under a minute. The page is then fitted in code.' })
    generate.mutate(
      { appId },
      {
        onSuccess: (v) => {
          setSelected(v.id)
          toast.success(`CV v${v.version} ready for review`, { id: t, description: `${v.page_count} page · ${Math.round((v.fill ?? 0) * 100)}% full · ${Math.round((v.duration_ms ?? 0) / 1000)}s` })
        },
        onError: (e) => toast.error(e.message, { id: t }),
      },
    )
  }, [appId, generate])

  useEffect(() => {
    if (params.get('generate') && studio.data && versions.length === 0 && !autoGenerated.current && !blockers.length) {
      autoGenerated.current = true
      setParams({}, { replace: true })
      runGenerate()
    }
  }, [params, studio.data, versions.length, runGenerate, setParams, blockers.length])

  const onApprove = () => {
    if (!version) return
    approve.mutate(version.id, {
      onSuccess: (r) => {
        const toEmail = r.next_step === 'draft_email'
        toast.success(`CV v${r.version.version} approved`, {
          description: toEmail ? 'Next: draft the cold email.' : 'Ready to apply: open the listing and send this CV.',
          duration: 10000,
          action: {
            label: toEmail ? 'Draft email' : 'Go to Ready to apply',
            onClick: () =>
              toEmail
                ? generateDraft.mutate(appId, { onSuccess: (d) => navigate(`/outreach?draft=${d.id}`), onError: (e) => toast.error(e.message) })
                : navigate('/applications?tab=ready'),
          },
        })
      },
      onError: (e) => toast.error(e.message),
    })
  }

  const error = job.error ?? studio.error
  const loading = job.isPending || (Number.isFinite(appId) && studio.isPending)
  const onePage = version?.page_count === 1 && !version.error

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
            CV Studio{job.data && <span className="font-normal text-fg-muted"> · {job.data.title}</span>}
          </p>
          <p className="truncate text-xs text-fg-subtle">
            {job.data ? `${job.data.company.name}${studio.data?.matched_track ? ` · ${studio.data.matched_track} track` : ''} · exactly one page, facts from your experience only` : ' '}
          </p>
        </div>
        {job.data && <StageBadge stage={job.data.application.stage} label={job.data.application.stage_label} />}
        {version && (
          <>
            <FitBadge version={version} />
            <span data-tour="cv-versions">
              <Select
                aria-label="Version"
                value={String(version.id)}
                onValueChange={(v) => setSelected(Number(v))}
                options={versions.map((v) => ({ value: String(v.id), label: `v${v.version} · ${STATUS_LABEL[v.status]} · ${relativeTime(v.created_at)}` }))}
                className="w-56"
              />
            </span>
            {templates.length > 1 && (
              <Select
                aria-label="Template"
                value={version.template}
                onValueChange={(template) => patch.mutate({ id: version.id, template }, { onError: (e) => toast.error(e.message) })}
                options={templates.map((t) => ({ value: t.name, label: `Template: ${t.name}` }))}
                className="w-44"
              />
            )}
            <Button onClick={runGenerate} disabled={generate.isPending || blockers.length > 0}>
              <RefreshCw className={generate.isPending ? 'animate-spin' : undefined} />
              {generate.isPending ? 'Generating…' : 'Regenerate'}
            </Button>
            <Tooltip content={studio.data?.download_name ?? 'Download PDF'}>
              <Button variant="ghost" size="icon" asChild disabled={!onePage}>
                <a href={apiUrl(`/cv/${version.id}/pdf`, { download: true })} aria-label="Download PDF">
                  <Download />
                </a>
              </Button>
            </Tooltip>
            <span data-tour="cv-approve">
              {version.status === 'approved' ? (
                <ToneBadge tone="green" dot={false} className="h-8 px-3 text-sm">
                  <CircleCheck className="size-4" />
                  Approved
                </ToneBadge>
              ) : (
                <Tooltip content={!onePage ? 'The CV must be exactly one page to approve' : null}>
                  <span>
                    <Button variant="default" onClick={onApprove} disabled={approve.isPending || version.status !== 'draft' || !onePage}>
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
            <Skeleton className="h-24" />
            <Skeleton className="h-40" />
            <Skeleton className="h-40" />
          </div>
          <Skeleton className="aspect-[1/1.294] w-full max-w-[620px]" />
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={() => (job.error ? job.refetch() : studio.refetch())} />
      ) : !version ? (
        <EmptyState
          icon={FileText}
          title={generate.isPending ? 'Tailoring your CV…' : 'No CV for this job yet'}
          description={
            blockers.length
              ? blockers.map((b) => b.message).join(' ')
              : 'One page, tailored to this listing from your experience pool. Nothing is invented: every fact is checked against what you entered.'
          }
          action={
            <div className="flex gap-2">
              {blockers.some((b) => b.key === 'full_name') ? (
                <Button variant="default" asChild>
                  <Link to="/settings?section=candidate">Open Candidate settings</Link>
                </Button>
              ) : (
                <Button variant="default" onClick={runGenerate} disabled={generate.isPending || blockers.length > 0}>
                  <Sparkles />
                  Generate CV
                </Button>
              )}
              <TourButton tour="cv" />
            </div>
          }
        />
      ) : studio.data ? (
        <Workspace key={version.id} studio={studio.data} version={version} />
      ) : null}
    </div>
  )
}
