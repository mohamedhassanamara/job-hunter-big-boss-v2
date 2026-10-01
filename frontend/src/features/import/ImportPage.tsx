import { BriefcaseBusiness, CircleCheck, ClipboardPaste, ExternalLink, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { FitBadge, SourceBadge, ToneBadge, type Tone } from '@/components/app/badges'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { useJob } from '@/lib/queries/jobs'
import { useCheckCapture, useCheckPaste, useImportJob } from '@/lib/queries/linkedin'
import type { LinkedInCapture, LinkedInImport } from '@/lib/types'
import { cn } from '@/lib/utils'

const HOW: Record<string, { label: string; tone: Tone }> = {
  'json-ld': { label: 'from the listing data', tone: 'green' },
  page: { label: 'from the page', tone: 'blue' },
  meta: { label: 'from the page title', tone: 'amber' },
  url: { label: 'from the URL', tone: 'slate' },
  you: { label: 'by you', tone: 'slate' },
  missing: { label: 'not found', tone: 'red' },
}
const STORE = 'jobhunter-capture'

/** The bookmark's data: the URL fragment (#c=…), else a postMessage from the LinkedIn tab,
 * else what this window already received (a reload). */
function readFragment(): Record<string, unknown> | null {
  const m = window.location.hash.match(/^#c=(.*)$/s)
  if (m) {
    try {
      const data = JSON.parse(decodeURIComponent(m[1]))
      sessionStorage.setItem(STORE, JSON.stringify(data))
      window.history.replaceState(null, '', window.location.pathname)
      return data
    } catch {
      return null
    }
  }
  try {
    const kept = sessionStorage.getItem(STORE)
    return kept ? JSON.parse(kept) : null
  } catch {
    return null
  }
}

function HowBadge({ how }: { how?: string }) {
  const h = HOW[how ?? 'missing'] ?? HOW.missing
  return (
    <ToneBadge tone={h.tone} dot={false} className="text-2xs">
      {h.label}
    </ToneBadge>
  )
}

function Field({ label, how, missing, children }: { label: string; how?: string; missing?: boolean; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <Label className={cn(missing && 'text-danger-fg')}>{label}</Label>
        <HowBadge how={how} />
      </div>
      {children}
    </div>
  )
}

function Result({ result }: { result: LinkedInImport }) {
  const job = useJob(result.job_id)
  const fit = job.data?.fit
  const scored = fit && fit.status !== 'pending' && fit.score != null
  // The fit arrives a few seconds after saving: poll the job until it's scored.
  const { refetch } = job
  useEffect(() => {
    if (scored) return
    const t = setInterval(() => void refetch(), 2000)
    return () => clearInterval(t)
  }, [scored, refetch])
  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface p-5">
      <p className="flex items-center gap-2 text-base font-semibold">
        <CircleCheck className="size-5 text-success-fg" />
        {result.created ? 'Saved to your jobs' : 'Already in your jobs: updated'}
      </p>
      {result.duplicate_of && (
        <p className="text-sm text-fg-muted">
          The same job came from <SourceBadge source={result.duplicate_of.source} /> too: it's linked as a duplicate, so you see it once.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-fg-muted">Fit</span>
        {scored ? <FitBadge fit={fit} /> : <span className="text-fg-subtle">{result.scoring.startsWith('blocked') ? result.scoring : 'Scoring this job…'}</span>}
        {result.matched_track && <ToneBadge tone="slate">{result.matched_track}</ToneBadge>}
      </div>
      {scored && job.data?.fit_detail?.summary && <p className="text-sm text-fg-muted">{job.data.fit_detail.summary}</p>}
      {result.warnings.map((w) => (
        <p key={w} className="flex items-start gap-2 text-xs text-warning-fg">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          {w}
        </p>
      ))}
      <div className="flex gap-2">
        <Button variant="default" size="sm" asChild>
          <a href={`/jobs/${result.job_id}`} target="jobhunter-app">
            Open the job
            <ExternalLink />
          </a>
        </Button>
        <Button size="sm" variant="ghost" onClick={() => window.close()}>
          Close this window
        </Button>
      </div>
    </div>
  )
}

/** The import window the LinkedIn bookmark opens: what was captured (and how), your edits,
 * then one save (deduped, track matched, scored on its own). A paste box when capture fails. */
export default function ImportPage() {
  const check = useCheckCapture()
  const paste = useCheckPaste()
  const save = useImportJob()
  const [form, setForm] = useState<LinkedInCapture | null>(null)
  const [raw, setRaw] = useState<Record<string, unknown> | null>(() => readFragment())
  const [waited, setWaited] = useState(false)
  const [pasteUrl, setPasteUrl] = useState('')
  const [pasteText, setPasteText] = useState('')
  const asked = useRef(false)

  // The second channel: ask the LinkedIn tab for the data (when the opener link survived).
  useEffect(() => {
    if (raw) return
    const onMessage = (e: MessageEvent) => {
      if (e.origin === 'https://www.linkedin.com' && e.data?.type === 'jobhunter-capture') setRaw(e.data.data)
    }
    window.addEventListener('message', onMessage)
    try {
      window.opener?.postMessage('jobhunter-ready', 'https://www.linkedin.com')
    } catch {
      /* no opener */
    }
    const t = setTimeout(() => setWaited(true), 2500)
    return () => {
      window.removeEventListener('message', onMessage)
      clearTimeout(t)
    }
  }, [raw])

  useEffect(() => {
    if (!raw || asked.current) return
    asked.current = true
    check.mutate(raw as never, { onSuccess: setForm, onError: (e) => toast.error(e.message) })
  }, [raw, check])

  const set = (k: keyof LinkedInCapture, v: string) =>
    setForm((f) => (f ? { ...f, [k]: v, sources: { ...f.sources, [k]: v.trim() ? (f.sources[k] === 'missing' ? 'you' : f.sources[k]) : 'missing' }, missing: f.missing.filter((m) => m !== k || !v.trim()) } : f))
  const missing = form ? (['title', 'company', 'description'] as const).filter((k) => !form[k].trim()) : []

  return (
    <div className="min-h-screen bg-bg">
      <div className="mx-auto max-w-3xl space-y-5 px-6 py-6">
        <div className="flex items-center gap-2">
          <BriefcaseBusiness className="size-5 text-primary" />
          <h1 className="text-lg font-semibold">Import from LinkedIn</h1>
          {form?.job_id && <span className="text-xs text-fg-subtle">Job {form.job_id}</span>}
        </div>

        {save.data ? (
          <Result result={save.data} />
        ) : !form && (check.isPending || (!raw && !waited)) ? (
          <div className="space-y-3">
            <Skeleton className="h-10" />
            <Skeleton className="h-40" />
          </div>
        ) : form ? (
          <form
            className="space-y-4 rounded-lg border border-border bg-surface p-5"
            onSubmit={(e) => {
              e.preventDefault()
              if (missing.length) return toast.error(`Fill in ${missing.join(', ')} first`)
              save.mutate(
                { url: form.url, job_id: form.job_id, title: form.title, company: form.company, company_url: form.company_url, location: form.location, workplace: form.workplace, description: form.description, poster: form.poster, sources: form.sources },
                { onError: (err) => toast.error(err.message) },
              )
            }}
          >
            {form.existing && (
              <p className="rounded-md bg-warning-bg px-3 py-2 text-sm text-warning-fg">
                Already in your list ({form.existing.how}: “{form.existing.title}”). Saving updates or links it; no second copy is made.
              </p>
            )}
            {form.warnings.map((w) => (
              <p key={w} className="flex items-start gap-2 text-xs text-warning-fg">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
                {w}
              </p>
            ))}
            <div className="grid grid-cols-2 gap-3">
              <Field label="Title" how={form.sources.title} missing={!form.title}>
                <Input value={form.title} onChange={(e) => set('title', e.target.value)} />
              </Field>
              <Field label="Company" how={form.sources.company} missing={!form.company}>
                <Input value={form.company} onChange={(e) => set('company', e.target.value)} />
              </Field>
              <Field label="Location" how={form.sources.location}>
                <Input value={form.location} onChange={(e) => set('location', e.target.value)} />
              </Field>
              <Field label="Workplace" how={form.sources.workplace}>
                <Input value={form.workplace} onChange={(e) => set('workplace', e.target.value)} placeholder="Remote, Hybrid or On-site" />
              </Field>
            </div>
            <Field label={`Description (${form.description.length.toLocaleString()} characters)`} how={form.sources.description} missing={!form.description}>
              <Textarea value={form.description} onChange={(e) => set('description', e.target.value)} className="min-h-56 text-xs" />
            </Field>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Label>Hiring team</Label>
                <HowBadge how={form.poster ? 'page' : 'missing'} />
              </div>
              {form.poster ? (
                <p className="text-sm">
                  {form.poster.name}
                  {form.poster.title && <span className="text-fg-muted"> · {form.poster.title}</span>}
                  {form.poster.url && (
                    <a href={form.poster.url} target="_blank" rel="noreferrer" className="ml-2 text-xs text-primary hover:underline">
                      profile
                    </a>
                  )}
                  <span className="block text-xs text-fg-subtle">Saved as the first person to message on LinkedIn for this job.</span>
                </p>
              ) : (
                <p className="text-xs text-fg-subtle">LinkedIn didn't show a hiring team on this page.</p>
              )}
            </div>
            <div className="flex items-center gap-2 border-t border-border pt-4">
              <Button type="submit" variant="default" disabled={save.isPending || missing.length > 0}>
                {save.isPending ? 'Saving…' : 'Save and score'}
              </Button>
              {missing.length > 0 && <span className="text-xs text-danger-fg">Missing: {missing.join(', ')}</span>}
              <span className="ml-auto truncate text-xs text-fg-subtle">{form.url}</span>
            </div>
          </form>
        ) : null}

        {!save.data && (!form || form.missing.length > 0) && (!raw || waited || check.isError) && (
          <div className="space-y-3 rounded-lg border border-border bg-surface p-5" data-tour="import-paste">
            <p className="flex items-center gap-2 text-sm font-medium">
              <ClipboardPaste className="size-4 text-fg-subtle" />
              {form ? 'Or paste the listing instead' : 'Nothing captured: paste the listing'}
            </p>
            <p className="text-xs text-fg-muted">On the LinkedIn job page: copy the address, then select the listing (title to the end of the description) and copy it.</p>
            <Input value={pasteUrl} onChange={(e) => setPasteUrl(e.target.value)} placeholder="https://www.linkedin.com/jobs/view/…" aria-label="Job URL" />
            <Textarea value={pasteText} onChange={(e) => setPasteText(e.target.value)} placeholder="The listing text" className="min-h-32 text-xs" aria-label="Listing text" />
            <Button
              size="sm"
              disabled={!pasteText.trim() || paste.isPending}
              onClick={() => paste.mutate({ url: pasteUrl, text: pasteText }, { onSuccess: setForm, onError: (e) => toast.error(e.message) })}
            >
              Read the pasted listing
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
