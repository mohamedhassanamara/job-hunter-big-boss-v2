import { CircleAlert, CircleCheck, ExternalLink, FileUp, RefreshCw, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { ErrorState, SkeletonRows } from '@/components/app/states'
import { TagInput } from '@/components/app/TagInput'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { apiUrl } from '@/lib/api'
import { useExperience, useSaveSetting, useSearchProfile } from '@/lib/queries/library'
import { useAddCVTemplate, useCVTemplates, useDeleteCVTemplate, useValidateCVTemplate } from '@/lib/queries/workflow'
import type { SettingsView } from '@/lib/types'
import { cn } from '@/lib/utils'
import { Card, Field, SaveBar } from './sections'

interface CVSettings {
  default_template: string
  filename_pattern: string
  track_emphasis: Record<string, { skill_groups?: string[]; tags?: string[] }>
}

const DEFAULTS: CVSettings = { default_template: 'default', filename_pattern: '{full_name}_CV_{company}.pdf', track_emphasis: {} }

function preview(pattern: string, name: string): string {
  return (
    pattern
      .replace('{full_name}', name || 'Your Name')
      .replace('{company}', 'Acme')
      .replace('{job_title}', 'Data Engineer')
      .replace('{version}', '1')
      .replace(/[^\w.\- ]+/g, '')
      .trim()
      .replace(/ /g, '_') || 'CV'
  ).replace(/(\.pdf)?$/i, '.pdf')
}

/** Settings → CV: download filename and what each track leads with. */
export function CVSettingsSection({ settings }: { settings: SettingsView }) {
  const initial: CVSettings = { ...DEFAULTS, ...((settings.values.cv as unknown as CVSettings | undefined) ?? {}) }
  const [v, setV] = useState<CVSettings>(initial)
  const save = useSaveSetting()
  const profile = useSearchProfile()
  const experience = useExperience()
  const dirty = JSON.stringify(v) !== JSON.stringify(initial)
  const groups = (experience.data ?? []).filter((i) => i.kind === 'skill').map((i) => i.title)
  const fullName = String((settings.values.profile as { full_name?: string } | undefined)?.full_name ?? '')
  const setTrack = (track: string, patch: { skill_groups?: string[]; tags?: string[] }) =>
    setV({ ...v, track_emphasis: { ...v.track_emphasis, [track]: { ...v.track_emphasis[track], ...patch } } })

  return (
    <Card
      title="CV"
      description="How tailored CVs are named, and what each track leads with. Content always comes from your Experience."
      footer={
        <SaveBar
          dirty={dirty}
          saving={save.isPending}
          onReset={() => setV(initial)}
          onSave={() =>
            save.mutate(
              { key: 'cv', value: v as unknown as Record<string, unknown> },
              { onSuccess: () => toast.success('CV settings saved'), onError: (e) => toast.error(e.message) },
            )
          }
        />
      }
    >
      <Field label="Download filename" hint="Fields: {full_name}, {company}, {job_title}, {version}">
        <Input value={v.filename_pattern} onChange={(e) => setV({ ...v, filename_pattern: e.target.value })} className="w-80 font-mono text-xs" aria-label="Filename pattern" />
        <p className="mt-1 text-xs text-fg-subtle">e.g. {preview(v.filename_pattern, fullName)}</p>
      </Field>
      <div data-tour="settings-cv-emphasis" className="space-y-3">
        <div>
          <Label className="text-sm text-fg">Track emphasis</Label>
          <p className="text-xs text-fg-subtle">
            For jobs in each track: which skill groups come first (click in order) and which tags the generator should lead with.
          </p>
        </div>
        {(profile.data?.tracks ?? []).filter((t) => t.name).map((track) => {
          const current = v.track_emphasis[track.name] ?? {}
          const order = current.skill_groups ?? []
          return (
            <div key={track.name} className="rounded-lg border border-border bg-bg-subtle p-3">
              <p className="text-sm font-medium">{track.name}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {groups.length === 0 && <span className="text-xs text-fg-subtle">Add skill groups in Experience first.</span>}
                {groups.map((g) => {
                  const idx = order.indexOf(g)
                  return (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setTrack(track.name, { skill_groups: idx >= 0 ? order.filter((x) => x !== g) : [...order, g] })}
                      className={cn(
                        'inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-xs transition-colors duration-120',
                        idx >= 0 ? 'border-primary bg-primary-subtle text-fg' : 'border-border-strong text-fg-muted hover:bg-surface-hover',
                      )}
                      aria-pressed={idx >= 0}
                    >
                      {idx >= 0 && <span className="font-semibold text-primary tabular-nums">{idx + 1}</span>}
                      {g}
                    </button>
                  )
                })}
              </div>
              <div className="mt-2">
                <TagInput tags={current.tags ?? []} onChange={(tags) => setTrack(track.name, { tags })} placeholder="Tags to lead with, e.g. flutter, riverpod (Enter)" />
              </div>
            </div>
          )
        })}
        {!(profile.data?.tracks ?? []).some((t) => t.name) && <p className="text-xs text-fg-subtle">Add tracks in Search profile first.</p>}
      </div>
    </Card>
  )
}

/** Settings → Templates: style-only CV templates. A template can be selected once it compiles
 * with fictional sample data on exactly one page. */
export function TemplatesSection({ settings }: { settings: SettingsView }) {
  const templates = useCVTemplates()
  const validate = useValidateCVTemplate()
  const remove = useDeleteCVTemplate()
  const save = useSaveSetting()
  const [adding, setAdding] = useState(false)
  const cv = { ...DEFAULTS, ...((settings.values.cv as unknown as CVSettings | undefined) ?? {}) }
  const setDefault = (name: string) =>
    save.mutate(
      { key: 'cv', value: { ...cv, default_template: name } as unknown as Record<string, unknown> },
      { onSuccess: () => { toast.success(`${name} is now the default template`); void templates.refetch() }, onError: (e) => toast.error(e.message) },
    )

  return (
    <Card
      title="Templates"
      description="A template is style only (layout, fonts, colours). Content comes from your data. See docs/CV_TEMPLATES.md for the contract."
      footer={
        <Button variant="default" size="sm" onClick={() => setAdding(true)}>
          <FileUp />
          Add template
        </Button>
      }
    >
      {templates.isPending ? (
        <SkeletonRows rows={2} />
      ) : templates.error ? (
        <ErrorState compact error={templates.error} onRetry={() => templates.refetch()} />
      ) : (
        <div data-tour="settings-templates" className="-mx-5 -my-4 divide-y divide-border">
          {templates.data.map((t) => (
            <div key={t.name} className="flex items-start gap-4 px-5 py-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold">{t.name}</p>
                  {t.is_default && (
                    <ToneBadge tone="blue">
                      <Star className="size-3" />
                      Default
                    </ToneBadge>
                  )}
                  <ToneBadge tone="gray" dot={false}>{t.paper === 'a4' ? 'A4' : 'Letter'}</ToneBadge>
                  {t.builtin && <span className="text-2xs text-fg-subtle">built in</span>}
                </div>
                {t.description && <p className="mt-0.5 text-xs text-fg-muted">{t.description}</p>}
                <p className={cn('mt-1 flex items-center gap-1.5 text-xs', t.valid ? 'text-success-fg' : 'text-danger-fg')}>
                  {t.valid ? <CircleCheck className="size-3.5" /> : <CircleAlert className="size-3.5" />}
                  {t.valid ? 'Compiles to one page with sample data' : t.error}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {t.valid && (
                  <Button variant="ghost" size="sm" asChild>
                    <a href={apiUrl(`/cv/templates/${encodeURIComponent(t.name)}/preview`)} target="_blank" rel="noreferrer">
                      <ExternalLink />
                      Preview
                    </a>
                  </Button>
                )}
                {!t.is_default && (
                  <Button variant="ghost" size="sm" disabled={!t.valid || save.isPending} onClick={() => setDefault(t.name)}>
                    Set default
                  </Button>
                )}
                <Button variant="ghost" size="icon-sm" aria-label={`Re-check ${t.name}`} disabled={validate.isPending} onClick={() => validate.mutate(t.name, { onError: (e) => toast.error(e.message) })}>
                  <RefreshCw className={validate.isPending ? 'animate-spin' : undefined} />
                </Button>
                {!t.builtin && !t.is_default && (
                  <Button variant="ghost" size="icon-sm" aria-label={`Delete ${t.name}`} onClick={() => remove.mutate(t.name, { onSuccess: () => toast.success(`${t.name} deleted`), onError: (e) => toast.error(e.message) })}>
                    <Trash2 />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {adding && <AddTemplateDialog onClose={() => setAdding(false)} />}
    </Card>
  )
}

function AddTemplateDialog({ onClose }: { onClose: () => void }) {
  const add = useAddCVTemplate()
  const [name, setName] = useState('')
  const [tex, setTex] = useState<{ file: string; text: string } | null>(null)
  const [config, setConfig] = useState<{ file: string; text: string } | null>(null)
  const read = (set: (v: { file: string; text: string }) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) void file.text().then((text) => set({ file: file.name, text }))
  }
  const submit = () =>
    add.mutate(
      { name, tex: tex?.text ?? '', config: config?.text ?? '' },
      {
        onSuccess: (t) => {
          if (t.valid) {
            toast.success(`Template ${t.name} added`, { description: 'It compiled to one page with sample data.' })
            onClose()
          } else toast.error(`Template ${t.name} saved but not usable yet`, { description: t.error ?? undefined })
        },
        onError: (e) => toast.error(e.message),
      },
    )
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Add a CV template" className="max-w-lg p-0">
        <div className="space-y-3 px-5 py-4">
          <div className="space-y-1">
            <h2 className="text-md font-semibold tracking-tight">Add a CV template</h2>
            <p className="text-sm text-fg-muted">
              A <span className="font-mono text-xs">cv.tex.j2</span> (LaTeX with <span className="font-mono text-xs">\VAR{'{…}'}</span> variables, no personal content) and a{' '}
              <span className="font-mono text-xs">cv.config.yaml</span>. It's compiled with sample data before it can be used.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="tpl-name">Name</Label>
            <Input id="tpl-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Compact two-column" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="tpl-tex">cv.tex.j2</Label>
              <Input id="tpl-tex" type="file" accept=".j2,.tex" onChange={read(setTex)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tpl-config">cv.config.yaml</Label>
              <Input id="tpl-config" type="file" accept=".yaml,.yml" onChange={read(setConfig)} />
            </div>
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" variant="default" onClick={submit} disabled={!name.trim() || !tex || !config || add.isPending}>
            {add.isPending ? 'Compiling sample…' : 'Add and check'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
