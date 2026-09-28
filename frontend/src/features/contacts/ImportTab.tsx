import { CircleCheck, CircleX, FileSpreadsheet, LoaderCircle, TriangleAlert, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { absoluteDate, pluralize } from '@/lib/format'
import { useImportPreview, useImportRun, useImports, useStartImport } from '@/lib/queries/library'
import type { FilePreview, ImportRun } from '@/lib/types'
import { cn } from '@/lib/utils'

const FIELDS: { key: string; label: string }[] = [
  { key: 'first_name', label: 'First name' },
  { key: 'last_name', label: 'Last name' },
  { key: 'full_name', label: 'Full name' },
  { key: 'title', label: 'Job title' },
  { key: 'email', label: 'Email' },
  { key: 'company', label: 'Company *' },
  { key: 'domain', label: 'Company website' },
  { key: 'linkedin_url', label: 'LinkedIn URL' },
]

const REASONS: Record<string, string> = {
  duplicate_in_file: 'duplicate in the file',
  already_known: 'already known',
  no_company: 'no company',
  no_name_or_email: 'no name or email',
}

interface Entry {
  file: File
  preview: FilePreview
  mapping: Record<string, string | null>
  include: boolean
}

function problems(m: Record<string, string | null>): string | null {
  if (!m.company) return 'Map the Company column'
  if (!m.email && !m.full_name && !m.first_name) return 'Map a name or an email column'
  return null
}

function summary(run: ImportRun): string {
  const skipped = Object.entries(run.skipped_reasons)
    .map(([k, v]) => `${v} ${REASONS[k] ?? k}`)
    .join(', ')
  return `${run.created} new · ${run.updated} updated · ${run.skipped} skipped${skipped ? ` (${skipped})` : ''} · ${pluralize(run.companies_created, 'new company', 'new companies')}`
}

/** One file of the batch: starts when it becomes active, polls until done, then hands over. */
function ImportFileRow({ entry, active, onFinished }: { entry: Entry; active: boolean; onFinished: () => void }) {
  const start = useStartImport()
  const [runId, setRunId] = useState<number | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const started = useRef(false)
  const run = useImportRun(runId)
  const finished = useRef(false)

  useEffect(() => {
    if (!active || started.current) return
    started.current = true
    start.mutate(
      { file: entry.file, mapping: entry.mapping, force: !!entry.preview.already_imported_at },
      {
        onSuccess: (r) => {
          setRunId(r.id)
          if (r.backup_path) toast.success('Database backed up', { description: r.backup_path })
        },
        onError: (e) => {
          setStartError(e.message)
          finished.current = true
          onFinished()
        },
      },
    )
  }, [active, entry, start, onFinished])

  const data = run.data
  useEffect(() => {
    if (data && data.status !== 'running' && !finished.current) {
      finished.current = true
      onFinished()
    }
  }, [data, onFinished])

  const pct = data ? Math.round((data.processed / Math.max(1, data.total)) * 100) : 0
  return (
    <div className="space-y-2 border-b border-border px-4 py-3 last:border-b-0">
      <div className="flex items-center gap-3">
        {startError || data?.status === 'failed' ? (
          <CircleX className="size-4 text-danger-fg" />
        ) : data?.status === 'done' ? (
          <CircleCheck className="size-4 text-success-dot" />
        ) : active ? (
          <LoaderCircle className="size-4 animate-spin text-fg-subtle" />
        ) : (
          <FileSpreadsheet className="size-4 text-fg-subtle" />
        )}
        <span className="flex-1 truncate text-sm font-medium">{entry.preview.filename}</span>
        <span className="text-xs text-fg-muted tabular-nums">
          {data ? `${data.processed} / ${data.total}` : active ? 'Starting…' : 'Waiting'}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-hover">
        <div className="h-full rounded-full bg-primary transition-all duration-300" style={{ width: `${pct}%` }} />
      </div>
      {data?.status === 'done' && <p className="text-xs text-fg-muted">{summary(data)}</p>}
      {(startError || data?.error) && <p className="text-xs text-danger-fg">{startError ?? data?.error}</p>}
    </div>
  )
}

function History() {
  const { data } = useImports()
  if (!data || data.length === 0) return null
  return (
    <div className="rounded-lg border border-border bg-surface">
      <p className="border-b border-border px-4 py-2.5 text-xs font-medium text-fg-subtle">Past imports</p>
      {data.slice(0, 10).map((r) => (
        <div key={r.id} className="flex items-center gap-3 border-b border-border px-4 py-2.5 text-sm last:border-b-0">
          <span className="w-56 truncate font-medium">{r.filename}</span>
          <span className="flex-1 truncate text-xs text-fg-muted">{r.status === 'failed' ? r.error : summary(r)}</span>
          <span className="text-xs whitespace-nowrap text-fg-subtle">{absoluteDate(r.started_at)}</span>
        </div>
      ))}
    </div>
  )
}

export function ImportTab() {
  const input = useRef<HTMLInputElement>(null)
  const [entries, setEntries] = useState<Entry[]>([])
  const [shown, setShown] = useState(0)
  const [running, setRunning] = useState(false)
  const [current, setCurrent] = useState(-1)
  const [dragging, setDragging] = useState(false)
  const preview = useImportPreview()

  const load = (files: File[]) => {
    const csvs = files.filter((f) => f.name.toLowerCase().endsWith('.csv'))
    if (csvs.length === 0) {
      toast.error('Choose .csv files exported from Apollo')
      return
    }
    preview.mutate(csvs, {
      onSuccess: (previews) => {
        // The same content twice (e.g. "list.csv" and "list (1).csv") is only imported once.
        const seen = new Set<string>()
        setEntries(
          previews.map((p, i) => {
            const dup = seen.has(p.sha256)
            seen.add(p.sha256)
            return { file: csvs[i], preview: p, mapping: p.mapping, include: !dup && !p.already_imported_at }
          }),
        )
        setShown(0)
      },
      onError: (e) => toast.error(e.message),
    })
  }

  const included = entries.filter((e) => e.include)
  const blocking = included.map((e) => problems(e.mapping)).find(Boolean)
  const done = running && current >= included.length
  const onFinished = () => setCurrent((c) => c + 1)
  const dupOf = (e: Entry, i: number) => entries.findIndex((x) => x.preview.sha256 === e.preview.sha256) !== i

  if (entries.length === 0) {
    return (
      <div className="mx-auto max-w-4xl space-y-5 px-6 py-6">
        <div
          data-tour="contacts-import"
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            load(Array.from(e.dataTransfer.files))
          }}
          className={cn(
            'flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors duration-120',
            dragging ? 'border-primary bg-primary-subtle' : 'border-border-strong bg-surface',
          )}
        >
          <div className="flex size-10 items-center justify-center rounded-lg border border-border bg-bg-subtle">
            <Upload className="size-5 text-fg-subtle" />
          </div>
          <div>
            <p className="text-base font-medium">Drop your Apollo CSV exports here</p>
            <p className="text-sm text-fg-muted">
              Several files at once is fine. Contacts are deduplicated by email, then by company + name, and matched to
              companies by name. The database is backed up before importing.
            </p>
          </div>
          <Button variant="default" size="sm" onClick={() => input.current?.click()} disabled={preview.isPending}>
            <FileSpreadsheet />
            {preview.isPending ? 'Reading…' : 'Choose files'}
          </Button>
          <input
            ref={input}
            type="file"
            multiple
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              load(Array.from(e.target.files ?? []))
              e.target.value = ''
            }}
          />
        </div>
        <History />
      </div>
    )
  }

  const focus = entries[shown]
  return (
    <div className="mx-auto max-w-5xl space-y-4 px-6 py-6">
      {!running ? (
        <>
          <div className="rounded-lg border border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <p className="text-sm font-semibold">{pluralize(entries.length, 'file')}</p>
              <Button size="sm" variant="ghost" onClick={() => setEntries([])}>
                Choose other files
              </Button>
            </div>
            {entries.map((e, i) => (
              <div
                key={`${e.preview.filename}-${i}`}
                className={cn(
                  'flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0',
                  shown === i && 'bg-surface-selected',
                )}
              >
                <Switch
                  checked={e.include}
                  aria-label={`Import ${e.preview.filename}`}
                  onCheckedChange={(v) => setEntries((all) => all.map((x, j) => (j === i ? { ...x, include: v } : x)))}
                />
                <button className="min-w-0 flex-1 text-left" onClick={() => setShown(i)}>
                  <p className="truncate text-sm font-medium">{e.preview.filename}</p>
                  <p className="text-xs text-fg-muted">
                    {pluralize(e.preview.total_rows, 'row')} · {e.preview.columns.join(', ')}
                  </p>
                </button>
                {dupOf(e, i) && <ToneBadge tone="gray">Same content as another file</ToneBadge>}
                {e.preview.already_imported_at && (
                  <ToneBadge tone="amber">Imported {absoluteDate(e.preview.already_imported_at)}</ToneBadge>
                )}
                {e.include && problems(e.mapping) && <ToneBadge tone="red">{problems(e.mapping)}</ToneBadge>}
              </div>
            ))}
          </div>

          {focus && (
            <div className="rounded-lg border border-border bg-surface">
              <div className="border-b border-border px-4 py-3">
                <p className="text-sm font-semibold">Column mapping · {focus.preview.filename}</p>
                <p className="text-xs text-fg-muted">Detected automatically. Adjust anything that looks wrong.</p>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 p-4">
                {FIELDS.map((f) => (
                  <div key={f.key} className="flex items-center gap-3">
                    <span className="w-36 text-sm text-fg-muted">{f.label}</span>
                    <Select
                      size="sm"
                      aria-label={f.label}
                      value={focus.mapping[f.key] ?? '__none'}
                      onValueChange={(v) =>
                        setEntries((all) =>
                          all.map((x, j) => (j === shown ? { ...x, mapping: { ...x.mapping, [f.key]: v === '__none' ? null : v } } : x)),
                        )
                      }
                      options={[{ value: '__none', label: 'Not mapped' }, ...focus.preview.columns.map((c) => ({ value: c, label: c }))]}
                      className="flex-1"
                    />
                  </div>
                ))}
              </div>
              <div className="overflow-x-auto border-t border-border">
                <table className="w-full text-xs">
                  <thead className="bg-bg-subtle">
                    <tr>
                      {focus.preview.columns.map((c) => (
                        <th key={c} className="h-8 px-3 text-left font-medium whitespace-nowrap text-fg-muted">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {focus.preview.sample.map((row, i) => (
                      <tr key={i} className="border-t border-border">
                        {focus.preview.columns.map((c) => (
                          <td key={c} className="h-8 max-w-48 truncate px-3 whitespace-nowrap">
                            {row[c] || <span className="text-fg-subtle">—</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="flex items-center justify-end gap-3">
            {blocking && (
              <span className="flex items-center gap-1.5 text-sm text-warning-fg">
                <TriangleAlert className="size-4" />
                {blocking}
              </span>
            )}
            <Button
              variant="default"
              disabled={!!blocking || included.length === 0}
              onClick={() => {
                setRunning(true)
                setCurrent(0)
              }}
            >
              Import {pluralize(included.length, 'file')} ({included.reduce((n, e) => n + e.preview.total_rows, 0).toLocaleString()} rows)
            </Button>
          </div>
        </>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg border border-border bg-surface">
            <p className="border-b border-border px-4 py-3 text-sm font-semibold">
              {done ? 'Import finished' : `Importing ${Math.min(current + 1, included.length)} of ${included.length}`}
            </p>
            {included.map((e, i) => (
              <ImportFileRow key={`${e.preview.sha256}-${i}`} entry={e} active={i <= current} onFinished={onFinished} />
            ))}
          </div>
          {done && (
            <div className="flex justify-end gap-2">
              <Button size="sm" onClick={() => {
                setEntries([])
                setRunning(false)
                setCurrent(-1)
              }}>
                Import more files
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
