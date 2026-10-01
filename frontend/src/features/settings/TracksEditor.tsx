import { ChevronDown, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { TagInput } from '@/components/app/TagInput'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { useSuggestVariants } from '@/lib/queries/library'
import type { Track, TrackRole, VariantLang } from '@/lib/types'
import { cn } from '@/lib/utils'

const LANGS: { code: VariantLang; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'fr', label: 'French' },
  { code: 'es', label: 'Spanish' },
  { code: 'de', label: 'German' },
  { code: 'it', label: 'Italian' },
  { code: 'nl', label: 'Dutch' },
]

const variantCount = (r: TrackRole) => Object.values(r.variants ?? {}).reduce((n, v) => n + (v?.length ?? 0), 0)

/** Settings → Search profile: the job titles to search for, grouped into tracks (Data/AI,
 * Mobile…) with your years in each. Sources query these titles plus their per-language
 * variants, the pre-filter matches them, and the scorer judges role and seniority per track. */
export function TracksEditor({ tracks, onChange }: { tracks: Track[]; onChange: (t: Track[]) => void }) {
  const setTrack = (i: number, patch: Partial<Track>) => onChange(tracks.map((t, j) => (j === i ? { ...t, ...patch } : t)))
  return (
    <div data-tour="settings-tracks" className="space-y-3">
      {tracks.length === 0 && (
        <p className="text-sm text-fg-muted">No roles yet. Add a track (e.g. “Mobile”) and the job titles you want. Discovery needs at least one role.</p>
      )}
      {tracks.map((track, i) => (
        <div key={i} className="rounded-lg border border-border bg-bg-subtle p-3">
          <div className="flex items-center gap-2">
            <Input
              value={track.name}
              onChange={(e) => setTrack(i, { name: e.target.value })}
              placeholder="Track name, e.g. Mobile"
              className="h-8 max-w-56 font-medium"
              aria-label="Track name"
            />
            <label className="flex items-center gap-1.5 text-xs text-fg-muted">
              Your years
              <Input
                type="number"
                min={0}
                step={0.5}
                value={track.years_experience ?? ''}
                onChange={(e) => setTrack(i, { years_experience: e.target.value === '' ? null : Number(e.target.value) })}
                className="h-8 w-20"
                aria-label={`Years of experience in ${track.name || 'this track'}`}
              />
            </label>
            <Select
              size="sm"
              value={track.experience ?? 'professional'}
              onValueChange={(v) => setTrack(i, { experience: v as 'professional' | 'projects' })}
              options={[
                { value: 'professional', label: 'Professional' },
                { value: 'projects', label: 'Projects only' },
              ]}
              aria-label={`Experience in ${track.name || 'this track'}`}
            />
            {track.experience === 'projects' && (
              <Input
                value={track.experience_note ?? ''}
                onChange={(e) => setTrack(i, { experience_note: e.target.value })}
                placeholder="How: personal projects, graduation project, internship…"
                className="h-8 min-w-48 flex-1 text-xs"
                aria-label={`How you gained ${track.name || 'this track'} experience`}
              />
            )}
            <div className="flex-1" />
            <Button variant="ghost" size="icon-sm" onClick={() => onChange(tracks.filter((_, j) => j !== i))} aria-label={`Remove track ${track.name}`}>
              <Trash2 />
            </Button>
          </div>
          <div className="mt-2 space-y-1.5">
            {track.roles.map((role, r) => (
              <RoleRow
                key={r}
                role={role}
                onChange={(next) => setTrack(i, { roles: track.roles.map((x, k) => (k === r ? next : x)) })}
                onRemove={() => setTrack(i, { roles: track.roles.filter((_, k) => k !== r) })}
              />
            ))}
            <Button variant="ghost" size="xs" onClick={() => setTrack(i, { roles: [...track.roles, { title: '', variants: null }] })}>
              <Plus /> Add role
            </Button>
          </div>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={() => onChange([...tracks, { name: '', years_experience: null, roles: [{ title: '', variants: null }] }])}>
        <Plus /> Add track
      </Button>
    </div>
  )
}

function RoleRow({ role, onChange, onRemove }: { role: TrackRole; onChange: (r: TrackRole) => void; onRemove: () => void }) {
  const [open, setOpen] = useState(false)
  const suggest = useSuggestVariants()
  const count = variantCount(role)
  const runSuggest = () => {
    if (!role.title.trim()) return
    suggest.mutate(role.title, {
      onSuccess: (variants) => {
        onChange({ ...role, variants })
        setOpen(true)
      },
      onError: (e) => toast.error(e.message),
    })
  }
  return (
    <div className="rounded-md border border-border bg-surface">
      <div className="flex items-center gap-2 px-2 py-1.5">
        <Input
          value={role.title}
          onChange={(e) => onChange({ ...role, title: e.target.value })}
          placeholder="Job title, e.g. Flutter Developer"
          className="h-7 flex-1 border-transparent bg-transparent px-1 shadow-none focus-visible:border-primary"
          aria-label="Role title"
        />
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="inline-flex items-center gap-1 text-xs text-fg-muted hover:text-fg"
          aria-expanded={open}
        >
          <ChevronDown className={cn('size-3.5 transition-transform duration-120', !open && '-rotate-90')} />
          {role.variants === null ? 'Variants suggested on save' : `${count} variant${count === 1 ? '' : 's'}`}
        </button>
        <Button variant="ghost" size="xs" onClick={runSuggest} disabled={!role.title.trim() || suggest.isPending}>
          <Sparkles /> Suggest
        </Button>
        <Button variant="ghost" size="icon-sm" onClick={onRemove} aria-label={`Remove ${role.title || 'role'}`}>
          <Trash2 />
        </Button>
      </div>
      {open && (
        <div className="grid gap-1.5 border-t border-border px-2 py-2 sm:grid-cols-[72px_minmax(0,1fr)]">
          {LANGS.map((lang) => (
            <div key={lang.code} className="contents">
              <span className="pt-1.5 text-2xs font-medium text-fg-subtle">{lang.label}</span>
              <TagInput
                tags={role.variants?.[lang.code] ?? []}
                onChange={(tags) => onChange({ ...role, variants: { ...(role.variants ?? {}), [lang.code]: tags } })}
                placeholder="Add a title (Enter)"
                lowercase={false}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
