import { ChevronDown, CircleAlert, ExternalLink, FlaskConical, KeyRound, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge, type Tone } from '@/components/app/badges'
import { ErrorState, SkeletonRows } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Tooltip } from '@/components/ui/tooltip'
import { absoluteDate, countryName, pluralize, reasonLabel, relativeTime, REMOTE_LABELS } from '@/lib/format'
import { useSaveSetting } from '@/lib/queries/library'
import { useSources, useTestSource } from '@/lib/queries/workflow'
import type { CompanyBoard, RunStatus, SampleJob, SettingsView, Source, SourceInfo, SourceTestResult } from '@/lib/types'
import { cn } from '@/lib/utils'
import { BoardsEditor } from './BoardsEditor'
import { Card } from './sections'

const NOTES: Record<Source, string> = {
  adzuna: 'Official API · searches each target country it has an endpoint for · short description snippets',
  remotive: 'Public API · remote jobs · fetched at most every 6h (Remotive asks for ≤ 4 requests/day) · every job links back to Remotive',
  arbeitnow: 'Public API · mostly German/DACH listings, so expect few matches',
  wttj: "Unofficial · uses the public search key from the Welcome to the Jungle website · summary + key missions only",
  boards: 'Official public job-board APIs (Greenhouse, Lever, Ashby, Workable, SmartRecruiters) of the companies below · full descriptions · at most every 6h',
  linkedin: 'Never fetched: LinkedIn jobs arrive only through your one-click import (LinkedIn section)',
  bayt: 'Public search pages of Bayt (Gulf/MENA), allowed by its robots.txt · one request per role × country, 3s apart, at most every 6h · short summaries (fetch the full listing per job)',
}

const STATUS: Record<RunStatus, { tone: Tone; label: string }> = {
  pending: { tone: 'gray', label: 'Pending' },
  running: { tone: 'blue', label: 'Running' },
  success: { tone: 'green', label: 'OK' },
  partial: { tone: 'amber', label: 'Partial' },
  failed: { tone: 'red', label: 'Failed' },
  skipped: { tone: 'gray', label: 'Skipped' },
}

function Counts({ run }: { run: NonNullable<SourceInfo['last_run']> }) {
  const items: [string, number][] = [
    ['fetched', run.fetched_count],
    ['kept', run.kept_count],
    ['filtered', run.filtered_count],
    ['new', run.new_count],
    ['updated', run.updated_count],
    [run.duplicate_count === 1 ? 'duplicate' : 'duplicates', run.duplicate_count],
  ]
  return (
    <span className="text-xs text-fg-muted tabular-nums">
      {items.map(([label, n], i) => (
        <span key={label}>
          {i > 0 && <span className="px-1 text-fg-subtle">·</span>}
          <span className="font-medium text-fg">{n}</span> {label}
        </span>
      ))}
    </span>
  )
}

function ReasonTable({ reasons }: { reasons: Record<string, number> }) {
  const entries = Object.entries(reasons)
  if (!entries.length) return <p className="text-xs text-fg-subtle">Nothing was filtered out.</p>
  return (
    <ul className="space-y-1">
      {entries.map(([reason, n]) => (
        <li key={reason} className="flex items-center justify-between gap-3 text-xs">
          <span className="text-fg-muted">{reasonLabel(reason)}</span>
          <span className="font-medium tabular-nums">{n}</span>
        </li>
      ))}
    </ul>
  )
}

function SampleList({ jobs, showReason }: { jobs: SampleJob[]; showReason?: boolean }) {
  if (!jobs.length) return <p className="text-sm text-fg-subtle">None.</p>
  return (
    <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
      {jobs.map((j, i) => (
        <li key={`${j.url}-${i}`} className="flex items-start gap-3 px-3 py-2">
          <div className="min-w-0 flex-1">
            <a href={j.url} target="_blank" rel="noreferrer" className="block truncate text-sm font-medium hover:underline">
              {j.title}
            </a>
            <p className="truncate text-xs text-fg-muted">
              {j.company} · {j.location || '—'}
              {!showReason && j.remote_type !== 'unknown' && ` · ${REMOTE_LABELS[j.remote_type]}`}
            </p>
          </div>
          {showReason && j.reason && (
            <span className="shrink-0 rounded-sm bg-surface-hover px-1.5 py-0.5 text-2xs text-fg-muted">
              {reasonLabel(j.reason)}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

function TestResultSheet({ result, name, onClose }: { result: SourceTestResult; name: string; onClose: () => void }) {
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        title={`Test: ${name}`}
        description="Dry run with your search profile. Nothing was saved."
        footer={<Button onClick={onClose}>Close</Button>}
      >
        <div className="space-y-5">
          <dl className="grid grid-cols-4 gap-3">
            {(
              [
                ['Fetched', result.fetched],
                ['Kept', result.kept],
                ['Filtered', result.filtered],
                ['Requests', result.requests],
              ] as const
            ).map(([label, n]) => (
              <div key={label} className="rounded-lg border border-border bg-bg-subtle px-3 py-2">
                <dt className="text-xs text-fg-subtle">{label}</dt>
                <dd className="text-lg font-semibold tabular-nums">{n}</dd>
              </div>
            ))}
          </dl>
          {result.warnings.map((w) => (
            <p key={w} className="flex items-center gap-2 rounded-md bg-warning-bg px-3 py-2 text-xs text-warning-fg">
              <TriangleAlert className="size-3.5" />
              {w}
            </p>
          ))}
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Would be kept ({result.kept})</h3>
            <SampleList jobs={result.kept_samples} />
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">Filtered out ({result.filtered})</h3>
            <div className="rounded-lg border border-border bg-bg-subtle p-3">
              <ReasonTable reasons={result.reasons} />
            </div>
            <SampleList jobs={result.filtered_samples} showReason />
          </section>
        </div>
      </SheetContent>
    </Sheet>
  )
}

function SourceRow({ info, onToggle, boards }: { info: SourceInfo; onToggle: (on: boolean) => void; boards?: CompanyBoard[] }) {
  const test = useTestSource()
  const [result, setResult] = useState<SourceTestResult | null>(null)
  const [reportOpen, setReportOpen] = useState(false)
  const run = info.last_run
  const reasons = run?.details.reasons ?? {}
  const samples = run?.details.samples ?? []
  const cooling = info.cooldown_remaining_minutes

  const runTest = () =>
    test.mutate(info.source, {
      onSuccess: setResult,
      onError: (e) => toast.error(e.message),
    })

  return (
    <div className="space-y-2.5 px-5 py-4">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold">{info.name}</p>
            {run && (
              <Tooltip content={absoluteDate(run.finished_at ?? run.started_at)}>
                <span>
                  <ToneBadge tone={STATUS[run.status].tone}>
                    {STATUS[run.status].label} · {relativeTime(run.finished_at ?? run.started_at)}
                  </ToneBadge>
                </span>
              </Tooltip>
            )}
            {!run && info.configured && <span className="text-xs text-fg-subtle">Never run</span>}
          </div>
          <p className="mt-0.5 text-xs text-fg-muted">{NOTES[info.source]}</p>
          {info.unsupported_countries.length > 0 && (
            <p className="mt-0.5 flex items-center gap-1 text-xs text-warning-fg">
              <TriangleAlert className="size-3.5 shrink-0" />
              Not supported by this source: {info.unsupported_countries.map(countryName).join(', ')}
            </p>
          )}
        </div>
        <Tooltip
          content={
            !info.configured
              ? 'Configure this source first'
              : cooling
                ? `Fetched recently: available again in ${cooling} min`
                : 'Dry run with your profile: shows what would be kept and filtered, saves nothing'
          }
        >
          <span>
            <Button size="sm" onClick={runTest} disabled={!info.configured || !!cooling || test.isPending}>
              <FlaskConical className={test.isPending ? 'animate-pulse' : undefined} />
              {test.isPending ? 'Testing…' : 'Test source'}
            </Button>
          </span>
        </Tooltip>
        <Switch
          checked={info.enabled}
          onCheckedChange={onToggle}
          aria-label={`Enable ${info.name}`}
          className="mt-1.5"
        />
      </div>

      {!info.configured && (
        <div className="flex items-start gap-2 rounded-md border border-tone-amber-border bg-warning-bg px-3 py-2 text-xs text-warning-fg">
          <KeyRound className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Not configured: {info.config_hint}.{' '}
            {info.source === 'adzuna' && (
              <a href="https://developer.adzuna.com" target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 font-medium underline-offset-2 hover:underline">
                Get a free key <ExternalLink className="size-3" />
              </a>
            )}
          </span>
        </div>
      )}

      {info.source === 'boards' && boards && <BoardsEditor boards={boards} results={run?.details.boards ?? {}} />}

      {cooling && (
        <p className="text-xs text-fg-subtle">
          Cooling down: next fetch allowed in {cooling >= 60 ? `${Math.floor(cooling / 60)}h ${cooling % 60}m` : `${cooling} min`}. Runs before then skip this source.
        </p>
      )}

      {run && (
        <div className="space-y-2">
          {run.status !== 'failed' && run.status !== 'skipped' && <Counts run={run} />}
          {run.error && !(run.error.startsWith('Not configured') && !info.configured) && (
            <div
              className={cn(
                'flex items-start gap-2 rounded-md px-3 py-2 text-xs',
                run.status === 'failed' ? 'bg-danger-bg text-danger-fg' : 'bg-bg-subtle text-fg-muted',
              )}
            >
              <CircleAlert className="mt-0.5 size-3.5 shrink-0" />
              <span className="break-words">{run.error}</span>
            </div>
          )}
          {run.details.warnings?.map((w) => (
            <p key={w} className="flex items-center gap-2 text-xs text-warning-fg">
              <TriangleAlert className="size-3.5" />
              {w}
            </p>
          ))}
          {run.filtered_count > 0 && (
            <div>
              <button
                onClick={() => setReportOpen((o) => !o)}
                className="inline-flex items-center gap-1 text-xs font-medium text-fg-muted hover:text-fg"
                aria-expanded={reportOpen}
              >
                <ChevronDown className={cn('size-3.5 transition-transform duration-120', !reportOpen && '-rotate-90')} />
                Filter report · {pluralize(run.filtered_count, 'job')} filtered
              </button>
              {reportOpen && (
                <div className="mt-2 grid gap-3 rounded-lg border border-border bg-bg-subtle p-3 lg:grid-cols-[240px_minmax(0,1fr)]">
                  <ReasonTable reasons={reasons} />
                  <div className="min-w-0">
                    <SampleList
                      jobs={samples.slice(0, 12).map((s) => ({ ...s, remote_type: 'unknown' as const }))}
                      showReason
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {result && <TestResultSheet result={result} name={info.name} onClose={() => setResult(null)} />}
    </div>
  )
}

export function SourcesSection({ settings }: { settings: SettingsView }) {
  const sources = useSources()
  const save = useSaveSetting()
  const flags = settings.values.sources as Record<Source, boolean>

  const toggle = (info: SourceInfo, on: boolean) =>
    save.mutate(
      { key: 'sources', value: { ...flags, [info.source]: on } },
      {
        onSuccess: () => {
          toast.success(`${info.name} ${on ? 'enabled' : 'disabled'}`)
          void sources.refetch()
        },
        onError: (e) => toast.error(e.message),
      },
    )

  return (
    <Card title="Sources" description="Where discovery pulls listings from. Toggles save immediately.">
      {sources.isPending ? (
        <SkeletonRows rows={4} />
      ) : sources.error ? (
        <ErrorState compact error={sources.error} onRetry={() => sources.refetch()} />
      ) : (
        <div className="-mx-5 -my-4 divide-y divide-border">
          {sources.data.map((info) => (
            <SourceRow
              key={info.source}
              info={info}
              onToggle={(on) => toggle(info, on)}
              boards={(settings.values.company_boards as { boards?: CompanyBoard[] } | undefined)?.boards ?? []}
            />
          ))}
          <div className="flex items-center gap-4 px-5 py-3 opacity-60">
            <div className="flex-1">
              <p className="text-sm font-semibold">LinkedIn</p>
              <p className="text-xs text-fg-muted">Not automated, by design. Browse it yourself.</p>
            </div>
            <Switch checked={false} disabled aria-label="LinkedIn (not available)" />
          </div>
        </div>
      )}
    </Card>
  )
}
