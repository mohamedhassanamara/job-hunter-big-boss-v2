import { CircleCheck, FileSpreadsheet, FlaskConical, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { pluralize } from '@/lib/format'
import { useImportContacts, useImportPreview } from '@/lib/queries/library'
import type { ImportPreview, ImportResult } from '@/lib/types'
import { cn } from '@/lib/utils'

const FIELDS: { key: string; label: string; required?: boolean }[] = [
  { key: 'full_name', label: 'Full name' },
  { key: 'first_name', label: 'First name' },
  { key: 'last_name', label: 'Last name' },
  { key: 'title', label: 'Job title' },
  { key: 'email', label: 'Email', required: true },
  { key: 'company', label: 'Company', required: true },
  { key: 'domain', label: 'Company website' },
  { key: 'linkedin_url', label: 'LinkedIn URL' },
]

const SAMPLE_CSV = `First Name,Last Name,Title,Company Name,Email,Website,Person Linkedin Url
Lucía,Ferrer,Head of Data,Nimbus Analytics,lucia.ferrer@nimbus-analytics.example,nimbus-analytics.example,https://linkedin.com/in/lucia-ferrer
Tiago,Moura,ML Lead,Quartzo Data,tiago.moura@quartzo.example,quartzo.example,https://linkedin.com/in/tiago-moura
Camille,Roux,MLOps Lead,Lumière Énergie,camille.roux@lumiere-energie.example,lumiere-energie.example,
Jonas,Weber,Head of AI,Pixelfarm Games,jonas.weber@pixelfarm.example,pixelfarm.example,https://linkedin.com/in/jonas-weber
Sara,Lindqvist,Engineering Manager,Kelpie,,kelpie.example,https://linkedin.com/in/sara-lindqvist
`

const STEPS = ['Upload', 'Map columns', 'Done']

export function ImportTab() {
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [mapping, setMapping] = useState<Record<string, string | null>>({})
  const [result, setResult] = useState<ImportResult | null>(null)
  const [dragging, setDragging] = useState(false)
  const previewMut = useImportPreview()
  const importMut = useImportContacts()
  const step = result ? 2 : preview ? 1 : 0

  const load = (f: File) => {
    if (!f.name.toLowerCase().endsWith('.csv')) {
      toast.error('Please choose a .csv file exported from Apollo')
      return
    }
    setFile(f)
    previewMut.mutate(f, {
      onSuccess: (p) => {
        setPreview(p)
        setMapping(p.mapping)
      },
      onError: (e) => toast.error(e.message),
    })
  }
  const reset = () => {
    setFile(null)
    setPreview(null)
    setResult(null)
  }
  const missing = FIELDS.filter((f) => f.required && !mapping[f.key])

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-6 py-6">
      <ol className="flex items-center gap-3 text-sm">
        {STEPS.map((s, i) => (
          <li key={s} className="flex items-center gap-3">
            <span
              className={cn(
                'flex items-center gap-2',
                i === step ? 'font-medium text-fg' : i < step ? 'text-fg-muted' : 'text-fg-subtle',
              )}
            >
              <span
                className={cn(
                  'flex size-5 items-center justify-center rounded-full border text-2xs font-semibold',
                  i < step
                    ? 'border-primary bg-primary text-primary-fg'
                    : i === step
                      ? 'border-primary text-primary'
                      : 'border-border-strong',
                )}
              >
                {i < step ? '✓' : i + 1}
              </span>
              {s}
            </span>
            {i < STEPS.length - 1 && <span className="h-px w-10 bg-border-strong" />}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <>
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              const f = e.dataTransfer.files[0]
              if (f) load(f)
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
              <p className="text-base font-medium">Drop your Apollo CSV export here</p>
              <p className="text-sm text-fg-muted">
                Contacts are matched to companies by domain and name. Existing contacts are updated, not duplicated.
              </p>
            </div>
            <div className="flex gap-2">
              <Button variant="default" size="sm" onClick={() => input.current?.click()} disabled={previewMut.isPending}>
                <FileSpreadsheet />
                Choose file
              </Button>
              <Button
                size="sm"
                onClick={() => load(new File([SAMPLE_CSV], 'apollo-sample.csv', { type: 'text/csv' }))}
                disabled={previewMut.isPending}
              >
                <FlaskConical />
                Try a sample file
              </Button>
            </div>
            <input
              ref={input}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) load(f)
                e.target.value = ''
              }}
            />
          </div>
          <p className="text-xs text-fg-subtle">
            Tip: in Apollo, export People with at least name, title, email and company. ~10k rows is fine.
          </p>
        </>
      )}

      {step === 1 && preview && (
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3">
            <div className="flex items-center gap-3">
              <FileSpreadsheet className="size-5 text-fg-subtle" />
              <div>
                <p className="text-sm font-medium">{preview.filename}</p>
                <p className="text-xs text-fg-muted">
                  {pluralize(preview.total_rows, 'row')} · {pluralize(preview.columns.length, 'column')}
                </p>
              </div>
            </div>
            <Button size="sm" variant="ghost" onClick={reset}>
              Choose another file
            </Button>
          </div>

          <div className="rounded-lg border border-border bg-surface">
            <div className="border-b border-border px-4 py-3">
              <p className="text-sm font-semibold">Column mapping</p>
              <p className="text-xs text-fg-muted">Detected automatically. Adjust anything that looks wrong.</p>
            </div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 p-4">
              {FIELDS.map((f) => (
                <div key={f.key} className="flex items-center gap-3">
                  <span className="w-36 text-sm text-fg-muted">
                    {f.label}
                    {f.required && <span className="text-danger-fg"> *</span>}
                  </span>
                  <Select
                    size="sm"
                    aria-label={f.label}
                    value={mapping[f.key] ?? '__none'}
                    onValueChange={(v) => setMapping((m) => ({ ...m, [f.key]: v === '__none' ? null : v }))}
                    options={[
                      { value: '__none', label: 'Not mapped' },
                      ...preview.columns.map((c) => ({ value: c, label: c })),
                    ]}
                    className="flex-1"
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-border bg-surface">
            <p className="border-b border-border px-4 py-2.5 text-xs font-medium text-fg-subtle">
              First {preview.sample.length} rows
            </p>
            <table className="w-full text-xs">
              <thead className="bg-bg-subtle">
                <tr>
                  {preview.columns.map((c) => (
                    <th key={c} className="h-8 px-3 text-left font-medium whitespace-nowrap text-fg-muted">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.sample.map((row, i) => (
                  <tr key={i} className="border-t border-border">
                    {preview.columns.map((c) => (
                      <td key={c} className="h-8 max-w-48 truncate px-3 whitespace-nowrap">
                        {row[c] || <span className="text-fg-subtle">—</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-end gap-3">
            {missing.length > 0 && (
              <span className="text-sm text-warning-fg">Map {missing.map((m) => m.label).join(' and ')} to continue</span>
            )}
            <Button
              variant="default"
              disabled={missing.length > 0 || importMut.isPending}
              onClick={() =>
                file &&
                importMut.mutate(file, {
                  onSuccess: setResult,
                  onError: (e) => toast.error(e.message),
                })
              }
            >
              Import {pluralize(preview.total_rows, 'contact')}
            </Button>
          </div>
        </div>
      )}

      {step === 2 && result && (
        <div className="rounded-lg border border-border bg-surface p-8 text-center">
          <CircleCheck className="mx-auto size-8 text-success-dot" />
          <p className="mt-3 text-md font-semibold">Import finished</p>
          <p className="text-sm text-fg-muted">
            {result.created} new · {result.updated} updated · {result.skipped} skipped (no email)
          </p>
          {result.mock && (
            <p className="mx-auto mt-3 max-w-md rounded-md bg-bg-subtle px-3 py-2 text-xs text-fg-muted">
              Phase 0 mock: nothing was written. The real importer arrives with the contacts slice.
            </p>
          )}
          <Button className="mt-5" size="sm" onClick={reset}>
            Import another file
          </Button>
        </div>
      )}
    </div>
  )
}
