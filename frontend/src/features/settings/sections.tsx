import { CircleCheck, Database, TriangleAlert } from 'lucide-react'
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
import { Tooltip } from '@/components/ui/tooltip'
import { COUNTRY_LABELS, relativeTime, SOURCE_LABELS } from '@/lib/format'
import { useResetData, useSaveSearchProfile, useSaveSetting } from '@/lib/queries/library'
import type { SearchProfile, SettingsView, Source } from '@/lib/types'
import { cn } from '@/lib/utils'

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

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
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

function SaveBar({ dirty, saving, onSave, onReset }: { dirty: boolean; saving: boolean; onSave: () => void; onReset: () => void }) {
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
      <Field label="Roles" hint="Title keywords to match">
        <TagInput tags={p.roles} onChange={(roles) => set({ roles })} placeholder="data engineer, ai engineer…" />
      </Field>
      <Field label="Boost keywords" hint="Raise relevance when present">
        <TagInput tags={p.keywords} onChange={(keywords) => set({ keywords })} />
      </Field>
      <Field label="Exclude keywords" hint="Skip listings containing these">
        <TagInput tags={p.excluded_keywords} onChange={(excluded_keywords) => set({ excluded_keywords })} placeholder="php, intern…" />
      </Field>
      <Field label="Countries">
        <div className="flex flex-wrap gap-1.5">
          {['ES', 'PT', 'FR', 'IT'].map((c) => {
            const on = p.locations.includes(c)
            return (
              <button
                key={c}
                onClick={() => set({ locations: on ? p.locations.filter((x) => x !== c) : [...p.locations, c] })}
                className={cn(
                  'inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-sm transition-colors duration-120',
                  on ? 'border-primary bg-primary-subtle text-fg' : 'border-border-strong text-fg-muted hover:bg-surface-hover',
                )}
                aria-pressed={on}
              >
                {on && <CircleCheck className="size-3.5 text-primary" />}
                {COUNTRY_LABELS[c]}
              </button>
            )
          })}
        </div>
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
          className="w-72"
        />
      </Field>
      <Field label="Highlight threshold" hint="Min fit for Today's highlights">
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={p.min_fit_score}
            onChange={(e) => set({ min_fit_score: Number(e.target.value) })}
            className="w-64 accent-(--primary)"
            aria-label="Minimum fit score"
          />
          <span className="w-8 text-sm font-medium tabular-nums">{p.min_fit_score}</span>
        </div>
      </Field>
    </Card>
  )
}

const SOURCE_NOTES: Record<Source, string> = {
  adzuna: 'Official API · broad EU coverage',
  remotive: 'Public API · remote-only roles',
  arbeitnow: 'Public API · EU tech jobs',
  wttj: 'Welcome to the Jungle · FR/ES startups',
}

export function SourcesSection({ settings }: { settings: SettingsView }) {
  const save = useSaveSetting()
  const flags = settings.values.sources as Record<Source, boolean>
  const runs = Object.fromEntries(settings.last_runs.map((r) => [r.source, r]))
  const toggle = (s: Source, on: boolean) =>
    save.mutate(
      { key: 'sources', value: { ...flags, [s]: on } },
      { onSuccess: () => toast.success(`${SOURCE_LABELS[s]} ${on ? 'enabled' : 'disabled'}`), onError: (e) => toast.error(e.message) },
    )
  return (
    <Card title="Sources" description="Where discovery pulls listings from. Toggles save immediately.">
      <div className="-mx-5 -my-4 divide-y divide-border">
        {(Object.keys(SOURCE_LABELS) as Source[]).map((s) => {
          const run = runs[s]
          return (
            <div key={s} className="flex items-center gap-4 px-5 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{SOURCE_LABELS[s]}</p>
                <p className="text-xs text-fg-muted">{SOURCE_NOTES[s]}</p>
              </div>
              {run && (
                <Tooltip content={run.error}>
                  <span className="flex items-center gap-1.5 text-xs text-fg-muted">
                    {run.status === 'success' ? (
                      <CircleCheck className="size-3.5 text-success-dot" />
                    ) : (
                      <TriangleAlert className="size-3.5 text-warning-dot" />
                    )}
                    Last run {relativeTime(run.finished_at ?? run.started_at)} · {run.new_count} new
                  </span>
                </Tooltip>
              )}
              <Switch checked={flags[s] ?? true} onCheckedChange={(on) => toggle(s, on)} aria-label={`Enable ${SOURCE_LABELS[s]}`} />
            </div>
          )
        })}
        <div className="flex items-center gap-4 px-5 py-3 opacity-60">
          <div className="flex-1">
            <p className="text-sm font-medium">LinkedIn</p>
            <p className="text-xs text-fg-muted">Not automated, by design. Browse it yourself.</p>
          </div>
          <Switch checked={false} disabled aria-label="LinkedIn (not available)" />
        </div>
      </div>
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
        <Input
          type="time"
          value={draft.value.time}
          disabled={!draft.value.enabled}
          onChange={(e) => draft.setValue({ ...draft.value, time: e.target.value })}
          className="w-32"
        />
      </Field>
    </Card>
  )
}

interface ModelsValue {
  scoring: { provider: string; model: string }
  cv: { provider: string; model: string }
  email: { provider: string; model: string }
}

const CLAUDE_MODELS = [
  { value: 'claude-opus-5-5', label: 'Claude Opus 5.5' },
  { value: 'claude-sonnet-5', label: 'Claude Sonnet 5' },
  { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' },
]

export function ModelsSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.models as unknown as ModelsValue
  const draft = useDraft(initial)
  const save = useSaveSetting()
  const m = draft.value
  return (
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
        <ToneBadge tone="amber">Mock</ToneBadge>
        Phase 0 runs deterministic mock providers regardless of these choices.
      </div>
      <Field label="Fit scoring" hint="Ollama, runs locally">
        <Input
          value={m.scoring.model}
          onChange={(e) => draft.setValue({ ...m, scoring: { ...m.scoring, model: e.target.value } })}
          className="w-64 font-mono text-xs"
        />
      </Field>
      <Field label="CV generation" hint="Anthropic API">
        <Select
          value={m.cv.model}
          onValueChange={(model) => draft.setValue({ ...m, cv: { ...m.cv, model } })}
          options={CLAUDE_MODELS}
          className="w-64"
        />
      </Field>
      <Field label="Email drafting" hint="Anthropic API">
        <Select
          value={m.email.model}
          onValueChange={(model) => draft.setValue({ ...m, email: { ...m.email, model } })}
          options={CLAUDE_MODELS}
          className="w-64"
        />
      </Field>
    </Card>
  )
}

export function EmailSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.smtp as { address: string; from_name: string; interval_minutes: number; max_per_queue: number }
  const draft = useDraft(initial)
  const save = useSaveSetting()
  return (
    <Card
      title="Email (Gmail SMTP)"
      description="Used by the send queue. Secrets never live in the database."
      footer={
        <SaveBar
          dirty={draft.dirty}
          saving={save.isPending}
          onReset={draft.reset}
          onSave={() => save.mutate({ key: 'smtp', value: draft.value }, { onSuccess: () => toast.success('Email settings saved') })}
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
      <Field label="Sending rules">
        <p className="pt-1.5 text-sm text-fg-muted">
          {draft.value.interval_minutes} min between sends · max {draft.value.max_per_queue} per queue
        </p>
      </Field>
    </Card>
  )
}

export function DataSection({ settings }: { settings: SettingsView }) {
  const reset = useResetData()
  const [confirm, setConfirm] = useState<null | 'demo' | 'empty'>(null)
  const run = (empty: boolean) =>
    reset.mutate(empty, {
      onSuccess: () => toast.success(empty ? 'Workspace emptied' : 'Demo data restored'),
      onError: (e) => toast.error(e.message),
      onSettled: () => setConfirm(null),
    })
  return (
    <Card title="Data" description="Local SQLite database. Everything stays on this machine.">
      <Field label="Database">
        <p className="flex items-center gap-2 pt-1.5 font-mono text-xs text-fg-muted">
          <Database className="size-3.5 text-fg-subtle" />
          {settings.database_path}
        </p>
      </Field>
      <Field label="Development" hint="Phase 0 helpers">
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setConfirm('demo')}>
            Reset demo data
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirm('empty')}>
            Start with an empty workspace
          </Button>
        </div>
      </Field>
      <Dialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent title="Reset data" className="max-w-md p-0">
          <div className="space-y-1 px-5 py-4">
            <h2 className="text-md font-semibold tracking-tight">
              {confirm === 'empty' ? 'Empty the workspace?' : 'Reset to demo data?'}
            </h2>
            <p className="text-sm text-fg-muted">
              This replaces every job, contact, CV and draft in the local database
              {confirm === 'empty' ? ' with an empty workspace' : ' with the mock dataset'}. It can't be undone.
            </p>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
            <Button size="sm" variant="ghost" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button size="sm" variant="danger" onClick={() => run(confirm === 'empty')} disabled={reset.isPending}>
              {confirm === 'empty' ? 'Empty workspace' : 'Reset data'}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
