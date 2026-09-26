import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { TagInput } from '@/components/app/TagInput'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import { Sheet, SheetContent } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import type { ExperienceInput, ExperienceItem, ExperienceKind } from '@/lib/types'
import { KINDS, KIND_META } from './kinds'

const toMonth = (d: string | null) => (d ? d.slice(0, 7) : '')
const fromMonth = (m: string) => (m ? `${m}-01` : null)

export function ExperienceSheet({
  open,
  item,
  defaultKind,
  saving,
  onClose,
  onSave,
  onDelete,
}: {
  open: boolean
  item: ExperienceItem | null
  defaultKind: ExperienceKind
  saving: boolean
  onClose: () => void
  onSave: (data: ExperienceInput) => void
  onDelete: (item: ExperienceItem) => void
}) {
  const [form, setForm] = useState<ExperienceInput>(
    item ?? {
      kind: defaultKind,
      title: '',
      org: null,
      location: null,
      start_date: null,
      end_date: null,
      summary: null,
      bullets: [],
      tags: [],
      is_active: true,
    },
  )
  const [present, setPresent] = useState(item ? !item.end_date && !!item.start_date : false)
  const set = (patch: Partial<ExperienceInput>) => setForm((f) => ({ ...f, ...patch }))
  const meta = KIND_META[form.kind]
  const datesApply = form.kind !== 'skill'
  const bulletsApply = form.kind !== 'skill' && form.kind !== 'certification'

  const submit = () =>
    onSave({
      ...form,
      title: form.title.trim(),
      end_date: present ? null : form.end_date,
      bullets: form.bullets.map((b) => b.trim()).filter(Boolean),
    })

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        title={item ? `Edit ${meta.singular.toLowerCase()}` : `Add ${meta.singular.toLowerCase()}`}
        description="Used as source material for tailored CVs and fit scoring."
        footer={
          <>
            {item && (
              <Button variant="ghost" className="mr-auto text-danger-fg hover:text-danger-fg" onClick={() => onDelete(item)}>
                <Trash2 />
                Delete
              </Button>
            )}
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="default" onClick={submit} disabled={!form.title.trim() || saving}>
              {item ? 'Save changes' : 'Add item'}
            </Button>
          </>
        }
      >
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            submit()
          }}
        >
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Type</Label>
              <Select
                value={form.kind}
                onValueChange={(v) => set({ kind: v as ExperienceKind })}
                options={KINDS.map((k) => ({ value: k.kind, label: k.singular }))}
                className="w-full"
              />
            </div>
            <div className="flex items-end justify-end pb-1.5">
              <label className="flex items-center gap-2 text-sm text-fg-muted">
                <Switch checked={form.is_active} onCheckedChange={(is_active) => set({ is_active })} />
                Use in CVs
              </label>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="title">{form.kind === 'skill' ? 'Group name' : 'Title'}</Label>
            <Input
              id="title"
              autoFocus
              value={form.title}
              onChange={(e) => set({ title: e.target.value })}
              placeholder={form.kind === 'job' ? 'Senior Data Engineer' : form.kind === 'skill' ? 'Data engineering' : ''}
            />
          </div>
          {form.kind !== 'skill' && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="org">{form.kind === 'education' ? 'School' : 'Organisation'}</Label>
                <Input id="org" value={form.org ?? ''} onChange={(e) => set({ org: e.target.value || null })} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="location">Location</Label>
                <Input
                  id="location"
                  value={form.location ?? ''}
                  onChange={(e) => set({ location: e.target.value || null })}
                />
              </div>
            </div>
          )}
          {datesApply && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="start">Start</Label>
                <Input
                  id="start"
                  type="month"
                  value={toMonth(form.start_date)}
                  onChange={(e) => set({ start_date: fromMonth(e.target.value) })}
                />
              </div>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="end">End</Label>
                  <label className="flex items-center gap-1.5 text-xs text-fg-muted">
                    <Checkbox checked={present} onCheckedChange={(v) => setPresent(v === true)} />
                    Present
                  </label>
                </div>
                <Input
                  id="end"
                  type="month"
                  disabled={present}
                  value={present ? '' : toMonth(form.end_date)}
                  onChange={(e) => set({ end_date: fromMonth(e.target.value) })}
                />
              </div>
            </div>
          )}
          {form.kind !== 'skill' && (
            <div className="space-y-1.5">
              <Label htmlFor="summary">Summary</Label>
              <Textarea
                id="summary"
                value={form.summary ?? ''}
                onChange={(e) => set({ summary: e.target.value || null })}
                className="min-h-16"
              />
            </div>
          )}
          {bulletsApply && (
            <div className="space-y-1.5">
              <Label>Achievements</Label>
              <p className="text-xs text-fg-subtle">
                Concrete, quantified bullets. The CV generator picks the most relevant ones per job.
              </p>
              <div className="space-y-1.5">
                {form.bullets.map((b, i) => (
                  <div key={i} className="flex items-start gap-1">
                    <Textarea
                      value={b}
                      rows={1}
                      onChange={(e) => set({ bullets: form.bullets.map((x, j) => (j === i ? e.target.value : x)) })}
                      className="field-sizing-content min-h-8 resize-none py-1.5 leading-5"
                    />
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      aria-label="Move up"
                      disabled={i === 0}
                      onClick={() => {
                        const next = [...form.bullets]
                        ;[next[i - 1], next[i]] = [next[i], next[i - 1]]
                        set({ bullets: next })
                      }}
                    >
                      <ArrowUp />
                    </Button>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      aria-label="Move down"
                      disabled={i === form.bullets.length - 1}
                      onClick={() => {
                        const next = [...form.bullets]
                        ;[next[i + 1], next[i]] = [next[i], next[i + 1]]
                        set({ bullets: next })
                      }}
                    >
                      <ArrowDown />
                    </Button>
                    <Button
                      type="button"
                      size="icon-sm"
                      variant="ghost"
                      aria-label="Remove bullet"
                      onClick={() => set({ bullets: form.bullets.filter((_, j) => j !== i) })}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                ))}
                <Button type="button" size="xs" variant="ghost" onClick={() => set({ bullets: [...form.bullets, ''] })}>
                  <Plus />
                  Add bullet
                </Button>
              </div>
            </div>
          )}
          <div className="space-y-1.5">
            <Label>{form.kind === 'skill' ? 'Skills' : 'Tags'}</Label>
            <TagInput tags={form.tags} onChange={(tags) => set({ tags })} />
          </div>
        </form>
      </SheetContent>
    </Sheet>
  )
}
