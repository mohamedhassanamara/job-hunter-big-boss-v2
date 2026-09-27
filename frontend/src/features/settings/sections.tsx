import { CircleCheck, Database } from 'lucide-react'
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
import { absoluteDate, COUNTRY_LABELS } from '@/lib/format'
import { useEraseWorkspace, useSaveSearchProfile, useSaveSetting } from '@/lib/queries/library'
import type { SearchProfile, SettingsView } from '@/lib/types'
import { cn } from '@/lib/utils'
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
      <Field
        label="Exclude title keywords"
        hint="Jobs whose title contains one of these are filtered out. Seniority is never filtered unless you add it here."
      >
        <TagInput tags={p.excluded_keywords} onChange={(excluded_keywords) => set({ excluded_keywords })} placeholder="intern, stage…" />
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
        Fit scoring runs on Ollama. CV generation and email drafting are still mocked.
      </div>
      <OllamaStatus />
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
