import { CircleAlert, CircleCheck, Copy, FlaskConical, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { useSaveSearchProfile, useSaveSetting, useSearchProfile } from '@/lib/queries/library'
import { useScoringHealth, useStartScoring } from '@/lib/queries/workflow'
import type { Dimension, SettingsView } from '@/lib/types'
import { Card } from './sections'

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

// ------------------------------------------------------------------------------ Candidate

interface Candidate {
  full_name: string
  email: string
  based_in: string
  work_authorization: 'needs_sponsorship' | 'eu_authorized'
  languages: { language: string; level: string }[]
  years_experience: number
  headline: string
  is_placeholder?: boolean
}

// CEFR levels plus the LinkedIn proficiency scale, for people who never took a CEFR test.
const LEVELS = [
  'Native', 'Full professional', 'Professional working', 'Limited working', 'Elementary',
  'C2', 'C1', 'B2', 'B1', 'A2', 'A1',
].map((l) => ({ value: l, label: l }))

export function CandidateSection({ settings }: { settings: SettingsView }) {
  const stored = settings.values.profile as unknown as Candidate
  const initial: Candidate = { ...stored, languages: stored.languages ?? [] }
  const [c, setC] = useState<Candidate>(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(c) !== JSON.stringify(initial)
  const set = (patch: Partial<Candidate>) => setC({ ...c, ...patch })

  return (
    <Card
      title="Candidate"
      description="How the fit scorer sees you. Used with your experience items in every score."
      footer={
        <SaveBar
          dirty={dirty}
          saving={save.isPending}
          onReset={() => setC(initial)}
          onSave={() =>
            save.mutate(
              // Once you edit the test profile, it's yours.
              { key: 'profile', value: { ...c, is_placeholder: false } as unknown as Record<string, unknown> },
              {
                onSuccess: () => toast.success('Candidate profile saved', { description: 'Existing scores are now stale; rescore from Discover.' }),
                onError: (e) => toast.error(e.message),
              },
            )
          }
        />
      }
    >
      {initial.is_placeholder && (
        <p className="flex items-center gap-2 rounded-md bg-warning-bg px-3 py-2 text-xs text-warning-fg">
          <FlaskConical className="size-3.5" />
          This is the test profile. Replace it with your details; saving makes it yours.
        </p>
      )}
      <Field label="Name">
        <Input value={c.full_name} onChange={(e) => set({ full_name: e.target.value })} className="w-80" />
      </Field>
      <Field label="Based in" hint="City and country">
        <Input value={c.based_in} onChange={(e) => set({ based_in: e.target.value })} placeholder="Tunis, Tunisia" className="w-80" />
      </Field>
      <Field label="Work authorization" hint="Decides which red flags disqualify a job">
        <Select
          value={c.work_authorization}
          onValueChange={(v) => set({ work_authorization: v as Candidate['work_authorization'] })}
          options={[
            { value: 'needs_sponsorship', label: 'I need visa sponsorship for the EU' },
            { value: 'eu_authorized', label: 'I can already work in the EU' },
          ]}
          className="w-80"
        />
      </Field>
      <Field label="Languages" hint="Compared with the languages a job requires">
        <div className="space-y-2">
          {c.languages.map((l, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input
                value={l.language}
                placeholder="Language"
                onChange={(e) => set({ languages: c.languages.map((x, j) => (j === i ? { ...x, language: e.target.value } : x)) })}
                className="w-48"
              />
              <Select
                aria-label="Level"
                value={l.level || 'B2'}
                onValueChange={(level) => set({ languages: c.languages.map((x, j) => (j === i ? { ...x, level } : x)) })}
                options={LEVELS}
                className="w-28"
              />
              <Button size="icon-sm" variant="ghost" aria-label="Remove language" onClick={() => set({ languages: c.languages.filter((_, j) => j !== i) })}>
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button size="xs" variant="ghost" onClick={() => set({ languages: [...c.languages, { language: '', level: 'B2' }] })}>
            <Plus />
            Add language
          </Button>
        </div>
      </Field>
      <Field label="Years of experience">
        <Input
          type="number"
          step={0.5}
          min={0}
          value={c.years_experience}
          onChange={(e) => set({ years_experience: Number(e.target.value) || 0 })}
          className="w-24"
        />
      </Field>
      <Field label="Headline" hint="One or two sentences about where you are and where you're going">
        <Textarea value={c.headline} onChange={(e) => set({ headline: e.target.value })} className="min-h-20" />
      </Field>
    </Card>
  )
}

// -------------------------------------------------------------------------------- Scoring

const DIMS: { key: Dimension; label: string }[] = [
  { key: 'role_match', label: 'Role match' },
  { key: 'skills_match', label: 'Skills' },
  { key: 'seniority_fit', label: 'Seniority' },
  { key: 'location_eligibility', label: 'Location & work auth' },
  { key: 'language_requirements', label: 'Languages' },
]
const EXAMPLE: Record<Dimension, number> = {
  role_match: 9,
  skills_match: 6,
  seniority_fit: 8,
  location_eligibility: 5,
  language_requirements: 10,
}

interface ScoringValue {
  weights: Record<Dimension, number>
  hard_flag_cap: number
  concurrency: number
  good_threshold: number
  maybe_threshold: number
}

const DEFAULT_SCORING: ScoringValue = {
  weights: { role_match: 0.3, skills_match: 0.3, seniority_fit: 0.15, location_eligibility: 0.15, language_requirements: 0.1 },
  hard_flag_cap: 35,
  concurrency: 1,
  good_threshold: 70,
  maybe_threshold: 45,
}

export function ScoringSection({ settings }: { settings: SettingsView }) {
  const stored = settings.values.scoring as unknown as Partial<ScoringValue> | undefined
  const initial: ScoringValue = { ...DEFAULT_SCORING, ...stored, weights: { ...DEFAULT_SCORING.weights, ...stored?.weights } }
  const profile = useSearchProfile()
  const [v, setV] = useState<ScoringValue>(initial)
  const [threshold, setThreshold] = useState<number | null>(null)
  const save = useSaveSetting()
  const saveProfile = useSaveSearchProfile()
  const currentThreshold = threshold ?? profile.data?.min_fit_score ?? 65
  const dirty = JSON.stringify(v) !== JSON.stringify(initial) || (threshold != null && threshold !== profile.data?.min_fit_score)
  const total = DIMS.reduce((a, d) => a + (v.weights[d.key] ?? 0), 0)
  const example = total ? Math.round((10 * DIMS.reduce((a, d) => a + (v.weights[d.key] ?? 0) * EXAMPLE[d.key], 0)) / total) : 0

  const onSave = async () => {
    try {
      await save.mutateAsync({ key: 'scoring', value: v as unknown as Record<string, unknown> })
      if (threshold != null && profile.data && threshold !== profile.data.min_fit_score) {
        await saveProfile.mutateAsync({ ...profile.data, min_fit_score: threshold })
      }
      setThreshold(null)
      toast.success('Scoring settings saved', { description: 'Every score was recomputed from its sub-scores (no model calls).' })
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <Card
      title="Scoring"
      description="The model gives 0–10 sub-scores; the 0–100 score is computed here, in code."
      footer={<SaveBar dirty={dirty} saving={save.isPending} onReset={() => { setV(initial); setThreshold(null) }} onSave={() => void onSave()} />}
    >
      <Field label="Weights" hint="Relative importance of each sub-score">
        <div className="space-y-2">
          {DIMS.map((d) => (
            <div key={d.key} className="flex items-center gap-3">
              <span className="w-40 text-sm">{d.label}</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={v.weights[d.key] ?? 0}
                onChange={(e) => setV({ ...v, weights: { ...v.weights, [d.key]: Number(e.target.value) } })}
                className="w-48 accent-(--primary)"
                aria-label={`${d.label} weight`}
              />
              <span className="w-12 text-right text-sm font-medium tabular-nums">
                {total ? Math.round(((v.weights[d.key] ?? 0) / total) * 100) : 0}%
              </span>
            </div>
          ))}
          <p className="pt-1 text-xs text-fg-muted">
            Example: role 9 · skills 6 · seniority 8 · location 5 · languages 10 →{' '}
            <span className="font-semibold text-fg tabular-nums">{example}</span>
          </p>
        </div>
      </Field>
      <Field label="Disqualifying flag cap" hint="Max score when a verified hard red flag applies to you">
        <Input type="number" min={0} max={100} value={v.hard_flag_cap} onChange={(e) => setV({ ...v, hard_flag_cap: Number(e.target.value) || 0 })} className="w-24" />
      </Field>
      <Field label="Shortlist threshold" hint="Divider in Discover and Today's highlights">
        <div className="flex items-center gap-3">
          <input type="range" min={0} max={100} step={5} value={currentThreshold} onChange={(e) => setThreshold(Number(e.target.value))} className="w-48 accent-(--primary)" aria-label="Shortlist threshold" />
          <span className="w-8 text-sm font-medium tabular-nums">{currentThreshold}</span>
        </div>
      </Field>
      <Field label="Eval buckets" hint="How make eval maps scores to Good / Maybe / No">
        <div className="flex items-center gap-2 text-sm text-fg-muted">
          Good ≥
          <Input type="number" value={v.good_threshold} onChange={(e) => setV({ ...v, good_threshold: Number(e.target.value) || 0 })} className="w-20" />
          Maybe ≥
          <Input type="number" value={v.maybe_threshold} onChange={(e) => setV({ ...v, maybe_threshold: Number(e.target.value) || 0 })} className="w-20" />
        </div>
      </Field>
      <Field label="Parallel jobs" hint="Scoring workers (1 keeps the laptop responsive)">
        <Select
          value={String(v.concurrency)}
          onValueChange={(c) => setV({ ...v, concurrency: Number(c) })}
          options={[
            { value: '1', label: '1 at a time' },
            { value: '2', label: '2 at a time' },
          ]}
          className="w-40"
        />
      </Field>
    </Card>
  )
}

// ---------------------------------------------------------------------------- Ollama status

export function OllamaStatus() {
  const { data, isPending, refetch } = useScoringHealth()
  const start = useStartScoring()
  if (isPending || !data) return <p className="text-xs text-fg-subtle">Checking Ollama…</p>
  return (
    <div className="space-y-2 rounded-md border border-border bg-bg-subtle px-3 py-2.5">
      <div className="flex items-center gap-2 text-sm">
        {data.reachable && data.model_present ? (
          <CircleCheck className="size-4 text-success-dot" />
        ) : (
          <CircleAlert className="size-4 text-danger-dot" />
        )}
        <span className="font-medium">
          {data.reachable ? (data.model_present ? `${data.model} is ready` : `${data.model} isn't pulled`) : 'Ollama isn’t running'}
        </span>
        <Button
          size="xs"
          variant="ghost"
          className="ml-auto"
          onClick={() => {
            void refetch()
            start.mutate(undefined, { onSuccess: () => toast.success('Scoring resumed') })
          }}
        >
          <RefreshCw />
          Check again
        </Button>
      </div>
      {!data.model_present && (
        <div className="flex items-center gap-2">
          <p className="text-xs text-fg-muted">{data.message}</p>
          {data.reachable && data.pull_command && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => {
                void navigator.clipboard.writeText(data.pull_command)
                toast.success('Command copied')
              }}
            >
              <Copy />
              <code className="font-mono">{data.pull_command}</code>
            </Button>
          )}
        </div>
      )}
      {data.models.length > 0 && <p className="text-2xs text-fg-subtle">Installed: {data.models.join(', ')}</p>}
    </div>
  )
}
