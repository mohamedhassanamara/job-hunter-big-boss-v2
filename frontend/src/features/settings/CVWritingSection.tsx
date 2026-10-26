import { useState } from 'react'
import { toast } from 'sonner'
import { TagInput } from '@/components/app/TagInput'
import { Input, Textarea } from '@/components/ui/input'
import { useSaveSetting } from '@/lib/queries/library'
import { formatRules, parseRules, type TrackTable } from './skillRules'
import type { SettingsView } from '@/lib/types'
import { Card, Field, SaveBar } from './sections'

type Range = [number, number]
interface Structure {
  current: Range
  long_role: Range
  long_role_months: number
  short_role: Range
  graduation: Range
  internship: Range
  projects_max: number
  project_min_relevance: number
  project_other_track_relevance: number
  project_bullets: Range
  volunteering_max: number
  skill_groups_max: number
  skill_items_max: number
  fill_min: number
  summary_max_words: number
  summary_max_sentences: number
}

const RANGES: { key: keyof Structure; label: string; hint?: string }[] = [
  { key: 'current', label: 'Current role' },
  { key: 'long_role', label: 'Roles over a year' },
  { key: 'graduation', label: 'Graduation project', hint: 'Up to the max when relevant to the track' },
  { key: 'short_role', label: 'Shorter roles', hint: 'Up to the max when relevant to the track' },
  { key: 'internship', label: 'Internships' },
  { key: 'project_bullets', label: 'Bullets per project', hint: 'Never a 1-bullet project' },
]

function RangeInput({ value, onChange, label }: { value: Range; onChange: (r: Range) => void; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <Input type="number" min={0} max={8} value={value[0]} onChange={(e) => onChange([Number(e.target.value), value[1]])} className="h-7 w-14" aria-label={`${label} minimum`} />
      to
      <Input type="number" min={0} max={8} value={value[1]} onChange={(e) => onChange([value[0], Number(e.target.value)])} className="h-7 w-14" aria-label={`${label} maximum`} />
      bullets
    </span>
  )
}

/** The writing guide (given to Claude) and the structure rules (applied in code). */
export function CVWritingSection({ settings }: { settings: SettingsView }) {
  const cv = (settings.values.cv ?? {}) as Record<string, unknown>
  const initial = {
    writing_guide: String(cv.writing_guide ?? ''),
    structure: cv.structure as Structure,
    skill_merges: ((cv.skill_merges as string[] | undefined) ?? []).join('\n'),
    banned_phrases: (cv.banned_phrases as string[] | undefined) ?? [],
    qualifiers: (cv.qualifiers as string[] | undefined) ?? [],
    skill_display: formatRules(cv.skill_display as TrackTable<string> | undefined),
    skill_keep: formatRules(cv.skill_keep as TrackTable<string[]> | undefined),
  }
  const [v, setV] = useState(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(v) !== JSON.stringify(initial)
  const s = v.structure
  const set = (patch: Partial<Structure>) => setV({ ...v, structure: { ...s, ...patch } })
  const num = (key: keyof Structure, label: string, props: { min?: number; max?: number; step?: number } = {}) => (
    <Input
      type="number"
      {...props}
      value={s[key] as number}
      onChange={(e) => set({ [key]: Number(e.target.value) } as Partial<Structure>)}
      className="h-7 w-20"
      aria-label={label}
    />
  )
  return (
    <Card
      title="How CVs are written"
      description="The guide is given to Claude with the reference CV as a style example; the structure rules and the summary checks are enforced in code (a summary that breaks them is regenerated once)."
      footer={
        <SaveBar
          dirty={dirty}
          saving={save.isPending}
          onReset={() => setV(initial)}
          onSave={() =>
            save.mutate(
              {
                key: 'cv',
                value: {
                  ...cv,
                  writing_guide: v.writing_guide,
                  banned_phrases: v.banned_phrases,
                  structure: v.structure,
                  skill_merges: v.skill_merges.split('\n').map((l) => l.trim()).filter(Boolean),
                  qualifiers: v.qualifiers,
                  skill_display: parseRules<string>(v.skill_display, false),
                  skill_keep: parseRules<string[]>(v.skill_keep, true),
                },
              },
              { onSuccess: () => toast.success('CV writing rules saved', { description: 'They apply to the next CV you generate.' }), onError: (e) => toast.error(e.message) },
            )
          }
        />
      }
    >
      <div data-tour="settings-cv-guide" className="space-y-1.5">
        <p className="text-sm font-medium">Writing guide</p>
        <Textarea value={v.writing_guide} onChange={(e) => setV({ ...v, writing_guide: e.target.value })} className="min-h-40 font-mono text-xs leading-5" aria-label="Writing guide" />
      </div>
      <Field label="Banned phrases" hint="Checked in every summary; a summary using one is rewritten once">
        <TagInput tags={v.banned_phrases} onChange={(banned_phrases) => setV({ ...v, banned_phrases })} placeholder="add a phrase (Enter)" />
      </Field>
      {RANGES.map((r) => (
        <Field key={r.key} label={r.label} hint={r.hint}>
          <RangeInput label={r.label} value={s[r.key] as Range} onChange={(range) => set({ [r.key]: range } as Partial<Structure>)} />
        </Field>
      ))}
      <Field label="A role counts as long after">
        <span className="inline-flex items-center gap-1.5 text-sm">{num('long_role_months', 'Long role months', { min: 1, max: 60 })} months</span>
      </Field>
      <Field label="Projects">
        <span className="inline-flex items-center gap-1.5 text-sm">at most {num('projects_max', 'Projects max', { min: 0, max: 4 })} projects</span>
      </Field>
      <Field label="Projects added to fill the page" hint="Roles fill first (current role, then the others by recency). A project bullet is added only at this relevance (out of 10), and never while a role bullet of the same relevance is left out. A project tagged only for other tracks needs the second number.">
        <span className="inline-flex items-center gap-1.5 text-sm">
          relevance {num('project_min_relevance', 'Project minimum relevance', { min: 0, max: 10 })}+, {num('project_other_track_relevance', 'Other-track project relevance', { min: 0, max: 10 })}+ for other tracks
        </span>
      </Field>
      <Field label="Skills">
        <span className="inline-flex items-center gap-1.5 text-sm">
          at most {num('skill_groups_max', 'Skill groups max', { min: 1, max: 8 })} groups of {num('skill_items_max', 'Skills per group', { min: 3, max: 15 })} skills
        </span>
      </Field>
      <Field label="Summary">
        <span className="inline-flex items-center gap-1.5 text-sm">
          at most {num('summary_max_sentences', 'Summary sentences', { min: 1, max: 4 })} sentences, about {num('summary_max_words', 'Summary words', { min: 20, max: 120 })} words
        </span>
      </Field>
      <Field label="Page fill target" hint="Never reached with filler: only within the allowances">
        <span className="inline-flex items-center gap-1.5 text-sm">
          <Input
            type="number"
            min={50}
            max={100}
            value={Math.round(s.fill_min * 100)}
            onChange={(e) => set({ fill_min: Number(e.target.value) / 100 })}
            className="h-7 w-20"
            aria-label="Page fill target"
          />
          % or more
        </span>
      </Field>
      <Field label="Summary qualifiers" hint="Words like “scalable” are only allowed in a summary when your experience says them; otherwise a warning">
        <TagInput tags={v.qualifiers} onChange={(qualifiers) => setV({ ...v, qualifiers })} placeholder="add a word (Enter)" />
      </Field>
      <Field label="Skill category names per track" hint="One per line: “Mobile | Backend & Data Engineering = Backend” shows that category as Backend on Mobile CVs">
        <Textarea value={v.skill_display} onChange={(e) => setV({ ...v, skill_display: e.target.value })} className="min-h-16 font-mono text-xs" aria-label="Skill category names per track" />
      </Field>
      <Field label="Skills kept first per track" hint="One per line: “Mobile | Core Languages = Kotlin, Swift”: pool skills pinned to the front of that group so the cap never drops them">
        <Textarea value={v.skill_keep} onChange={(e) => setV({ ...v, skill_keep: e.target.value })} className="min-h-16 font-mono text-xs" aria-label="Skills kept first per track" />
      </Field>
      <Field label="Skill merges" hint="One per line: “LLMs: Mistral, Ollama” · “LocalStack + S3” · “Linux / Bash”">
        <Textarea value={v.skill_merges} onChange={(e) => setV({ ...v, skill_merges: e.target.value })} className="min-h-24 font-mono text-xs" aria-label="Skill merges" />
      </Field>
    </Card>
  )
}
