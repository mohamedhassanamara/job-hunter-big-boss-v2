import { Database } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { TagInput } from '@/components/app/TagInput'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { absoluteDate } from '@/lib/format'
import { useEraseWorkspace, useSaveSearchProfile, useSaveSetting } from '@/lib/queries/library'
import type { RemoteScope, SearchProfile, SettingsView } from '@/lib/types'
import { CountryPicker } from './CountryPicker'
import { TracksEditor } from './TracksEditor'
import { OllamaStatus } from './ScoringSections'

export function Card({
  title,
  description,
  children,
  footer,
}: {
  title: string
  description?: string
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  return (
    <section className="rounded-lg border border-border bg-surface shadow-sm">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-md font-semibold tracking-tight">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-fg-muted">{description}</p>}
      </div>
      <div className="space-y-4 px-5 py-4">{children}</div>
      {footer && <div className="flex items-center justify-end gap-3 border-t border-border px-5 py-3">{footer}</div>}
    </section>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[200px_1fr] items-start gap-4">
      <div className="pt-1.5">
        <Label className="text-sm text-fg">{label}</Label>
        {hint && <p className="text-xs text-fg-subtle">{hint}</p>}
      </div>
      <div>{children}</div>
    </div>
  )
}

export function SaveBar({ dirty, saving, onSave, onReset }: { dirty: boolean; saving: boolean; onSave: () => void; onReset: () => void }) {
  return (
    <>
      {dirty && <span className="mr-auto text-xs text-fg-subtle">Unsaved changes</span>}
      <Button variant="ghost" size="sm" onClick={onReset} disabled={!dirty}>
        Discard
      </Button>
      <Button variant="default" size="sm" onClick={onSave} disabled={!dirty || saving}>
        Save
      </Button>
    </>
  )
}

function useDraft<T>(initial: T) {
  const [value, setValue] = useState<T>(initial)
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  return { value, setValue, dirty, reset: () => setValue(initial) }
}

// ---------------------------------------------------------------------------------------------

export function ProfileSection({ profile }: { profile: SearchProfile }) {
  const draft = useDraft(profile)
  const save = useSaveSearchProfile()
  const p = draft.value
  const set = (patch: Partial<SearchProfile>) => draft.setValue({ ...p, ...patch })
  return (
    <Card
      title="Search profile"
      description="What discovery looks for. Changes apply from the next run."
      footer={
        <SaveBar
          dirty={draft.dirty}
          saving={save.isPending}
          onReset={draft.reset}
          onSave={() => save.mutate(p, { onSuccess: () => toast.success('Search profile saved'), onError: (e) => toast.error(e.message) })}
        />
      }
    >
      <Field label="Profile name">
        <Input value={p.name} onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field label="Roles & tracks" hint="The job titles you want, grouped by field. Sources search each title and its variants; the scorer judges role and seniority against the track a job matched.">
        <TracksEditor tracks={p.tracks ?? []} onChange={(tracks) => set({ tracks })} />
      </Field>
      <Field label="Boost keywords" hint="Raise relevance when present">
        <TagInput tags={p.keywords} onChange={(keywords) => set({ keywords })} />
      </Field>
      <Field
        label="Exclude title keywords"
        hint="Jobs whose title contains one of these are filtered out. Seniority is never filtered unless you add it here."
      >
        <TagInput tags={p.excluded_keywords} onChange={(excluded_keywords) => set({ excluded_keywords })} placeholder="intern, stage…" />
      </Field>
      <Field label="Countries" hint="Jobs must be in one of these (on-site and hybrid). Sources search every country they support.">
        <CountryPicker selected={p.locations} onChange={(locations) => set({ locations })} />
      </Field>
      <Field label="Remote">
        <Select
          value={p.remote_policy}
          onValueChange={(v) => set({ remote_policy: v as SearchProfile['remote_policy'] })}
          options={[
            { value: 'any', label: 'Any (remote, hybrid, on-site)' },
            { value: 'remote_ok', label: 'Remote or hybrid preferred' },
            { value: 'remote_only', label: 'Remote only' },
          ]}
          className="w-80"
        />
      </Field>
      <Field label="Remote scope" hint="Which remote jobs count. US-only (or any Americas / Asia-only) remote is never eligible.">
        <Select
          value={p.remote_scope}
          onValueChange={(v) => set({ remote_scope: v as RemoteScope })}
          options={[
            { value: 'anywhere', label: 'Remote anywhere (worldwide or EMEA)' },
            { value: 'europe', label: 'Remote Europe' },
            { value: 'targets', label: 'Remote in my target countries only' },
          ]}
          className="w-80"
        />
      </Field>
      <Field label="Max job age" hint="Skip listings posted longer ago than this">
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={1}
            max={120}
            value={p.max_age_days}
            onChange={(e) => set({ max_age_days: Math.max(1, Number(e.target.value) || 1) })}
            className="w-20"
          />
          <span className="text-sm text-fg-muted">days</span>
        </div>
      </Field>
    </Card>
  )
}

export function ScheduleSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.schedule as { enabled: boolean; time: string }
  const draft = useDraft(initial)
  const save = useSaveSetting()
  return (
    <Card
      title="Schedule"
      description="When the daily discovery run happens (local time, via APScheduler)."
      footer={
        <SaveBar
          dirty={draft.dirty}
          saving={save.isPending}
          onReset={draft.reset}
          onSave={() => save.mutate({ key: 'schedule', value: draft.value }, { onSuccess: () => toast.success('Schedule saved') })}
        />
      }
    >
      <Field label="Daily discovery">
        <Switch checked={draft.value.enabled} onCheckedChange={(enabled) => draft.setValue({ ...draft.value, enabled })} />
      </Field>
      <Field label="Run at">
        <div className="flex items-center gap-3">
          <Input
            type="time"
            value={draft.value.time}
            disabled={!draft.value.enabled}
            onChange={(e) => draft.setValue({ ...draft.value, time: e.target.value })}
            className="w-32"
          />
          <span className="text-xs text-fg-muted">
            {settings.next_run_at && initial.enabled
              ? `Next run: ${absoluteDate(settings.next_run_at)}`
              : 'Not scheduled'}
          </span>
        </div>
      </Field>
    </Card>
  )
}

interface ModelsValue {
  scoring: {
    provider: string
    model: string
    fallback?: string
    cloud_concurrency?: { min: number; start: number; max: number }
    local_concurrency?: number
  }
  cv: GeneratorValue
  email: GeneratorValue
  letter?: GeneratorValue
}

/** CV / email generator: Gemini (shared free keys) or Claude; thinking applies to Gemini only. */
interface GeneratorValue {
  provider: string
  model: string
  thinking_level?: string
}

const GENERATOR_MODELS = [
  { value: 'gemini-3.5-flash-lite', label: 'Gemini 3.5 Flash-Lite (free keys)' },
  { value: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash-Lite (free keys)' },
  { value: 'claude-opus-5-5', label: 'Claude Opus 5.5' },
  { value: 'claude-sonnet-5', label: 'Claude Sonnet 5' },
]

/** The CV is the only generator that can use the APInex gateway (email and letters never do). */
const CV_MODELS = [{ value: 'free/minimax-m3.1-flash', label: 'MiniMax M3.1 Flash (APInex)' }, ...GENERATOR_MODELS]

const SCORING_MODELS = [
  { value: 'free/minimax-m3.1-flash', label: 'MiniMax M3.1 Flash (APInex)' },
  { value: 'free/gpt-6-luna', label: 'GPT-6 Luna (APInex)' },
  { value: 'free/glm-5.3-flash', label: 'GLM 5.3 Flash (APInex)' },
  { value: 'free/mimo-v2.6-pro', label: 'Mimo V2.6 Pro (APInex)' },
  { value: 'qwen2.5:7b', label: 'Qwen 2.5 7B (Ollama Local)' },
  { value: 'gemma4:12b', label: 'Gemma 4 12B (Ollama Local)' },
  { value: 'gemma4:31b-cloud', label: 'Gemma 4 31B (Ollama Cloud)' },
  { value: 'llama3.3:70b-cloud', label: 'Llama 3.3 70B (Ollama Cloud)' },
]

const SCORING_FALLBACK_MODELS = [
  { value: 'qwen2.5:7b', label: 'Qwen 2.5 7B (Ollama Local - Recommended)' },
  { value: 'gemma4:12b', label: 'Gemma 4 12B (Ollama Local)' },
  { value: 'gemma4:31b-cloud', label: 'Gemma 4 31B (Ollama Cloud)' },
  { value: 'llama3.3:70b-cloud', label: 'Llama 3.3 70B (Ollama Cloud)' },
]
const THINKING_LEVELS = [
  { value: 'minimal', label: 'No thinking (minimal)' },
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'dynamic', label: 'Dynamic (the model decides)' },
]

function providerOf(model: string): string {
  return model.startsWith('gemini-') ? 'gemini' : model.startsWith('free/') ? 'apinex' : 'anthropic'
}

function generatorOf(m: GeneratorValue | undefined, fallback = 'gemini-3.5-flash-lite'): GeneratorValue {
  const model = m?.model && !m.model.startsWith('claude-haiku') ? m.model : fallback
  return { provider: providerOf(model), model, thinking_level: m?.thinking_level ?? 'minimal' }
}

function GeneratorField({ label, hint, value, onChange, models = GENERATOR_MODELS, fallback }: { label: string; hint: string; value: GeneratorValue | undefined; onChange: (v: GeneratorValue) => void; models?: typeof GENERATOR_MODELS; fallback?: string }) {
  const g = generatorOf(value, fallback)
  const gemini = g.model.startsWith('gemini-')
  return (
    <Field label={label} hint={hint}>
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={g.model}
          onValueChange={(model) => onChange({ ...g, model, provider: providerOf(model) })}
          options={models}
          className="w-72"
          aria-label={`${label} model`}
        />
        {gemini && <Select value={g.thinking_level ?? 'minimal'} onValueChange={(thinking_level) => onChange({ ...g, thinking_level })} options={THINKING_LEVELS} className="w-52" aria-label={`${label} thinking`} />}
      </div>
    </Field>
  )
}

interface GenerationValue {
  auto_cv: boolean
  auto_email: boolean
}

export function ModelsSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.models as unknown as ModelsValue
  const draft = useDraft(initial)
  const save = useSaveSetting()
  const m = draft.value
  const cloud = { min: 1, start: 4, max: 4, ...m.scoring.cloud_concurrency }
  const setCloud = (c: typeof cloud) => {
    const min = Math.min(c.min, c.max)
    const max = Math.max(c.min, c.max)
    draft.setValue({ ...m, scoring: { ...m.scoring, cloud_concurrency: { min, max, start: Math.min(max, Math.max(min, c.start)) } } })
  }
  const quotaModel = [m.cv?.model, m.email?.model].find((x) => x?.startsWith('gemini-'))
  return (
    <>
    <Card
      title="Models"
      description="Which model backs each step. Providers are swappable behind interfaces."
      footer={
        <SaveBar
          dirty={draft.dirty}
          saving={save.isPending}
          onReset={draft.reset}
          onSave={() =>
            save.mutate({ key: 'models', value: m as unknown as Record<string, unknown> }, { onSuccess: () => toast.success('Models saved') })
          }
        />
      }
    >
      <div className="flex items-center gap-2 rounded-md bg-bg-subtle px-3 py-2 text-xs text-fg-muted">
        <ToneBadge tone="green">Live</ToneBadge>
        Scoring runs through the APInex Gateway (15 RPM) with automatic Ollama fallback. The CV is written through the APInex Gateway too (2-pass) unless you pick Gemini or Claude below; email generation shares the free Gemini keys (one pooled quota; what you trigger goes first). Claude stays the claim verifier, Critique and Ask Claude.
      </div>
      <Field label="Fit scoring" hint="Primary scoring model. APInex gateway models run with strict 15 RPM rolling throttle.">
        <Select
          value={m.scoring.model}
          onValueChange={(model) => draft.setValue({ ...m, scoring: { ...m.scoring, model, provider: model.startsWith('free/') ? 'apinex' : 'ollama' } })}
          options={SCORING_MODELS}
          className="w-80"
          aria-label="Scoring model"
        />
      </Field>
      <Field label="Ollama fallback" hint="Used automatically for the rest of a run when APInex quota is exhausted or rate limit is reached.">
        <Select
          value={m.scoring.fallback ?? 'qwen2.5:7b'}
          onValueChange={(fallback) => draft.setValue({ ...m, scoring: { ...m.scoring, fallback } })}
          options={SCORING_FALLBACK_MODELS}
          className="w-80"
          aria-label="Fallback model"
        />
      </Field>
      <Field label="Cloud parallel jobs" hint="Adaptive: drops by 1 on each “too many concurrent requests”, climbs back after a streak of successes.">
        <div className="flex items-center gap-2 text-xs text-fg-muted">
          {(['min', 'start', 'max'] as const).map((k) => (
            <label key={k} className="flex items-center gap-1.5">
              {k === 'min' ? 'Min' : k === 'start' ? 'Start' : 'Max'}
              <Select
                size="sm"
                value={String(cloud[k])}
                onValueChange={(v) => setCloud({ ...cloud, [k]: Number(v) })}
                options={[1, 2, 3, 4, 5, 6, 7, 8].map((n) => ({ value: String(n), label: String(n) }))}
                aria-label={`Cloud concurrency ${k}`}
              />
            </label>
          ))}
        </div>
      </Field>
      <Field label="Local parallel jobs" hint="For local models (and the fallback). Use 1 if the Mac gets sluggish.">
        <Select
          value={String(m.scoring.local_concurrency ?? 2)}
          onValueChange={(v) => draft.setValue({ ...m, scoring: { ...m.scoring, local_concurrency: Number(v) } })}
          options={[
            { value: '1', label: '1 at a time' },
            { value: '2', label: '2 at a time' },
          ]}
          className="w-40"
        />
      </Field>
      <div className="space-y-2">
        {m.scoring.model.startsWith('free/') ? (
          <div className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2 text-xs text-fg-muted">
            <ToneBadge tone="green">APInex Gateway</ToneBadge>
            <span>15 RPM rolling throttle active · Automatic Ollama fallback on exhaustion ({m.scoring.fallback || 'qwen2.5:7b'})</span>
          </div>
        ) : (
          <OllamaStatus label="Scoring" />
        )}
        {m.scoring.fallback && <OllamaStatus model={m.scoring.fallback} label="Fallback" />}
        {quotaModel && (
          <details className="rounded-md border border-border bg-surface px-3 py-2 text-xs text-fg-muted">
            <summary className="cursor-default font-medium text-fg">Are my keys separate projects? (check in AI Studio)</summary>
            <ol className="mt-2 list-decimal space-y-1 pl-4">
              <li>Open aistudio.google.com/apikey: each key row shows the Google Cloud project it belongs to.</li>
              <li>Keys under different project names have separate daily quotas; keys under the same project share one.</li>
              <li>Open aistudio.google.com/rate-limit and pick a project: its requests per minute and per day for {quotaModel} are listed. Make one test call with key N and only that project&apos;s count moves.</li>
              <li>The pooled number above counts what this app sent. Other tools using the same keys are only visible on Google&apos;s page.</li>
            </ol>
          </details>
        )}
      </div>
      <GeneratorField
        label="CV generation"
        hint="Writes the CV plan; checks, the one-page fit and the claim verifier stay as they are. Failures never switch model: you get Retry and Generate with Claude."
        value={m.cv}
        onChange={(cv) => draft.setValue({ ...m, cv })}
        models={CV_MODELS}
        fallback="free/minimax-m3.1-flash"
      />
      <GeneratorField
        label="Email generation"
        hint="Writes the application follow-up (and the intro). Claude verifies every claim when you click Approve."
        value={m.email}
        onChange={(email) => draft.setValue({ ...m, email })}
      />
      <Field label="Letter generator" hint="Cover letters, form text and application answers. Always Claude Code (your subscription); independent of the CV and email models.">
        <Select
          value={m.letter?.model?.startsWith('claude-') ? m.letter.model : 'claude-sonnet-5'}
          onValueChange={(model) => draft.setValue({ ...m, letter: { provider: 'anthropic', model } })}
          options={GENERATOR_MODELS.filter((o) => o.value.startsWith('claude-'))}
          className="w-64"
          aria-label="Letter generator model"
        />
      </Field>
    </Card>
    <AutomationCard settings={settings} />
    </>
  )
}

/** Background drafting (services/generation.py): drafts only, never approves, no toasts. */
function AutomationCard({ settings }: { settings: SettingsView }) {
  const initial = (settings.values.generation as unknown as GenerationValue | undefined) ?? { auto_cv: true, auto_email: false }
  const draft = useDraft(initial)
  const save = useSaveSetting()
  const g = draft.value
  return (
    <Card
      title="Automatic drafting"
      description="Drafts only: nothing is approved or sent for you, and nothing pops up. A badge on the job says when a draft is ready."
      footer={
        <SaveBar dirty={draft.dirty} saving={save.isPending} onReset={draft.reset} onSave={() => save.mutate({ key: 'generation', value: g as unknown as Record<string, unknown> }, { onSuccess: () => toast.success('Automatic drafting saved') })} />
      }
    >
      <div data-tour="automation" className="space-y-4">
        <Field label="Draft the CV when I shortlist a job" hint="Queued in the background as a draft. Skipped when the job already has a CV or your experience is incomplete (a warning shows on the job). Un-shortlisting cancels it if it hasn't started.">
          <Switch checked={g.auto_cv} onCheckedChange={(v) => draft.setValue({ ...g, auto_cv: v })} aria-label="Auto-generate the CV" />
        </Field>
        <Field label="Draft the email when the contact and the CV are both ready" hint="Needs a verified contact AND an approved CV on a job you shortlisted, and only for jobs with a posting (the application follow-up). Off until you have compared the Gemini and Claude emails.">
          <Switch checked={g.auto_email} onCheckedChange={(v) => draft.setValue({ ...g, auto_email: v })} aria-label="Auto-generate the email" />
        </Field>
      </div>
    </Card>
  )
}

export function EmailSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.smtp as { address: string; from_name: string; gap_min_minutes: number; gap_max_minutes: number; max_per_queue: number }
  const draft = useDraft(initial)
  const save = useSaveSetting()
  const { gap_min_minutes: lo, gap_max_minutes: hi } = draft.value
  const gapError = !(lo >= 1) ? 'The minimum must be at least 1 minute' : lo > hi ? 'The minimum can’t be above the maximum' : null
  return (
    <Card
      title="Email (Gmail SMTP)"
      description="Used by the send queue. Secrets never live in the database."
      footer={
        <SaveBar
          dirty={draft.dirty && !gapError}
          saving={save.isPending}
          onReset={draft.reset}
          onSave={() => save.mutate({ key: 'smtp', value: draft.value }, { onSuccess: () => toast.success('Email settings saved'), onError: (e) => toast.error(e.message) })}
        />
      }
    >
      <Field label="Gmail address">
        <Input
          type="email"
          placeholder="you@gmail.com"
          value={draft.value.address}
          onChange={(e) => draft.setValue({ ...draft.value, address: e.target.value })}
          className="w-80"
        />
      </Field>
      <Field label="From name">
        <Input
          placeholder="Your Name"
          value={draft.value.from_name}
          onChange={(e) => draft.setValue({ ...draft.value, from_name: e.target.value })}
          className="w-80"
        />
      </Field>
      <Field label="App password">
        <div className="flex items-center gap-2 pt-1">
          <ToneBadge tone={settings.smtp_password_configured ? 'green' : 'gray'}>
            {settings.smtp_password_configured ? 'Configured' : 'Not configured'}
          </ToneBadge>
          <span className="text-xs text-fg-muted">
            Set <code className="rounded-sm bg-surface-hover px-1 font-mono">SMTP_APP_PASSWORD</code> in <code className="rounded-sm bg-surface-hover px-1 font-mono">.env</code>
          </span>
        </div>
      </Field>
      <Field label="Gap between sends" hint="A random gap after every email, drawn fresh between the minimum and maximum (uniform). The planned next send is stored, so a restart keeps the schedule and never sends early or twice.">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-sm">
            <Input type="number" min={1} step={0.5} value={lo} onChange={(e) => draft.setValue({ ...draft.value, gap_min_minutes: Number(e.target.value) })} className="h-8 w-20" aria-label="Minimum gap in minutes" />
            to
            <Input type="number" min={1} step={0.5} value={hi} onChange={(e) => draft.setValue({ ...draft.value, gap_max_minutes: Number(e.target.value) })} className="h-8 w-20" aria-label="Maximum gap in minutes" />
            minutes
          </div>
          {gapError && <p className="text-xs text-danger-fg" role="alert">{gapError}</p>}
          <p className="text-xs text-fg-muted">Max {draft.value.max_per_queue} per queue.</p>
        </div>
      </Field>
    </Card>
  )
}

export function DataSection({ settings }: { settings: SettingsView }) {
  const erase = useEraseWorkspace()
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const close = () => {
    setOpen(false)
    setTyped('')
  }
  return (
    <Card title="Data" description="Local SQLite database. Everything stays on this machine.">
      <Field label="Database">
        <p className="flex items-center gap-2 pt-1.5 font-mono text-xs text-fg-muted">
          <Database className="size-3.5 text-fg-subtle" />
          {settings.database_path}
        </p>
      </Field>
      <Field label="Sample data" hint="Only ever used inside guided tours">
        <p className="pt-1.5 text-sm text-fg-muted">
          Your workspace contains only your real data. Tours run on a separate sandbox that is
          rebuilt every time a tour starts. Start one from the <span className="font-medium">?</span> menu
          in the top bar.
        </p>
      </Field>
      <Field label="Erase my workspace" hint="Jobs, contacts, CVs, drafts, experience">
        <Button size="sm" variant="ghost" className="text-danger-fg hover:text-danger-fg" onClick={() => setOpen(true)}>
          Erase all data…
        </Button>
      </Field>
      <Dialog open={open} onOpenChange={(o) => !o && close()}>
        <DialogContent title="Erase workspace" className="max-w-md p-0">
          <div className="space-y-3 px-5 py-4">
            <div className="space-y-1">
              <h2 className="text-md font-semibold tracking-tight">Erase your workspace?</h2>
              <p className="text-sm text-fg-muted">
                This permanently deletes every job, contact, CV, draft and experience item. Your
                search profile and settings are kept. It can't be undone.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="erase-confirm">Type ERASE to confirm</Label>
              <Input id="erase-confirm" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
            </div>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
            <Button size="sm" variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={typed !== 'ERASE' || erase.isPending}
              onClick={() =>
                erase.mutate(typed, {
                  onSuccess: () => {
                    toast.success('Workspace erased')
                    close()
                  },
                  onError: (e) => toast.error(e.message),
                })
              }
            >
              Erase everything
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

interface TrackingValue {
  followup_days: number[]
  ghost_after_days: number
}

export function TrackingSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.tracking as unknown as TrackingValue
  const draft = useDraft(initial)
  const save = useSaveSetting()
  const [days, setDays] = useState(initial.followup_days.join(', '))
  const parsed = days
    .split(/[,\s]+/)
    .filter(Boolean)
    .map(Number)
  const valid = parsed.length > 0 && parsed.every((d) => Number.isInteger(d) && d >= 1 && d <= 365)
  const ghostValid = Number.isInteger(draft.value.ghost_after_days) && draft.value.ghost_after_days >= 1 && draft.value.ghost_after_days <= 365
  return (
    <Card
      title="Tracking"
      description="Follow-up reminders after you apply. They are computed on the fly, so a change applies right away."
      footer={
        <SaveBar
          dirty={draft.dirty || days !== initial.followup_days.join(', ')}
          saving={save.isPending}
          onReset={() => {
            draft.reset()
            setDays(initial.followup_days.join(', '))
          }}
          onSave={() =>
            valid && ghostValid
              ? save.mutate(
                  { key: 'tracking', value: { ...draft.value, followup_days: [...new Set(parsed)].sort((a, b) => a - b) } },
                  { onSuccess: () => toast.success('Tracking saved'), onError: (e) => toast.error(e.message) },
                )
              : toast.error('Days must be whole numbers from 1 to 365')
          }
        />
      }
    >
      <Field label="Follow up after (days)">
        <div className="space-y-1">
          <Input value={days} onChange={(e) => setDays(e.target.value)} className="w-40" aria-invalid={!valid} />
          <p className="text-xs text-fg-muted">Comma-separated, e.g. 7, 14. Only the latest due one shows, and a reply or interview stops them.</p>
        </div>
      </Field>
      <Field label="Suggest closing as no response after (days)">
        <div className="space-y-1">
          <Input
            type="number"
            min={1}
            max={365}
            value={draft.value.ghost_after_days}
            onChange={(e) => draft.setValue({ ...draft.value, ghost_after_days: Number(e.target.value) })}
            className="w-24"
            aria-invalid={!ghostValid}
          />
          <p className="text-xs text-fg-muted">Only a suggestion on Today: the application closes when you confirm.</p>
        </div>
      </Field>
    </Card>
  )
}
