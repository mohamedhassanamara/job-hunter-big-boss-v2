import { Award, Briefcase, FlaskConical, FolderGit2, GraduationCap, HeartHandshake, type LucideIcon, TextQuote, Wrench } from 'lucide-react'
import type { ExperienceKind } from '@/lib/types'

export const KINDS: { kind: ExperienceKind; label: string; singular: string; icon: LucideIcon; note?: string }[] = [
  { kind: 'summary', label: 'Summary snippets', singular: 'Summary snippet', icon: TextQuote },
  { kind: 'job', label: 'Work experience', singular: 'Role', icon: Briefcase },
  { kind: 'project', label: 'Projects', singular: 'Project', icon: FolderGit2 },
  { kind: 'volunteering', label: 'Volunteering & leadership', singular: 'Volunteering role', icon: HeartHandshake },
  { kind: 'skill', label: 'Skills', singular: 'Skill group', icon: Wrench },
  {
    kind: 'skill_proof',
    label: 'Skill proofs',
    singular: 'Skill proof',
    icon: FlaskConical,
    note: 'Never printed in Experience. Small real projects that prove a skill: only the skills line of a job CV can use them, and only when a listing names the skill.',
  },
  { kind: 'education', label: 'Education', singular: 'Education', icon: GraduationCap },
  { kind: 'certification', label: 'Certifications', singular: 'Certification', icon: Award },
]

export const KIND_META = Object.fromEntries(KINDS.map((k) => [k.kind, k])) as Record<
  ExperienceKind,
  (typeof KINDS)[number]
>

export function formatRange(start: string | null, end: string | null) {
  if (!start) return null
  const f = (d: string) => new Date(d).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
  return `${f(start)} – ${end ? f(end) : 'Present'}`
}
