import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tooltip } from '@/components/ui/tooltip'
import type { CVContent, CVEntry } from '@/lib/types'

type Update = (next: CVContent) => void

function move<T>(list: T[], from: number, to: number): T[] {
  if (to < 0 || to >= list.length) return list
  const copy = [...list]
  const [item] = copy.splice(from, 1)
  copy.splice(to, 0, item)
  return copy
}

function IconAction({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string
  onClick: () => void
  disabled?: boolean
  children: React.ReactNode
}) {
  return (
    <Tooltip content={label}>
      <Button size="icon-sm" variant="ghost" onClick={onClick} disabled={disabled} aria-label={label}>
        {children}
      </Button>
    </Tooltip>
  )
}

function Group({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-b border-border px-5 py-4 last:border-b-0">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  )
}

function BulletList({
  bullets,
  onChange,
  readOnly,
}: {
  bullets: string[]
  onChange: (b: string[]) => void
  readOnly: boolean
}) {
  return (
    <div className="space-y-1.5">
      {bullets.map((b, i) => (
        <div key={i} className="group flex items-start gap-1">
          <span className="mt-2.5 size-1 shrink-0 rounded-full bg-fg-subtle" />
          <Textarea
            value={b}
            readOnly={readOnly}
            onChange={(e) => onChange(bullets.map((x, j) => (j === i ? e.target.value : x)))}
            rows={1}
            className="field-sizing-content min-h-8 resize-none py-1.5 leading-5"
          />
          {!readOnly && (
            <div className="flex opacity-0 transition-opacity duration-120 group-focus-within:opacity-100 group-hover:opacity-100">
              <IconAction label="Move up" onClick={() => onChange(move(bullets, i, i - 1))} disabled={i === 0}>
                <ArrowUp />
              </IconAction>
              <IconAction
                label="Move down"
                onClick={() => onChange(move(bullets, i, i + 1))}
                disabled={i === bullets.length - 1}
              >
                <ArrowDown />
              </IconAction>
              <IconAction label="Remove bullet" onClick={() => onChange(bullets.filter((_, j) => j !== i))}>
                <Trash2 />
              </IconAction>
            </div>
          )}
        </div>
      ))}
      {!readOnly && (
        <Button size="xs" variant="ghost" onClick={() => onChange([...bullets, ''])}>
          <Plus />
          Add bullet
        </Button>
      )}
    </div>
  )
}

function EntryList({
  entries,
  onChange,
  readOnly,
  withBullets = true,
  empty,
}: {
  entries: CVEntry[]
  onChange: (e: CVEntry[]) => void
  readOnly: boolean
  withBullets?: boolean
  empty: CVEntry
}) {
  const set = (i: number, patch: Partial<CVEntry>) =>
    onChange(entries.map((e, j) => (j === i ? { ...e, ...patch } : e)))
  return (
    <div className="space-y-3">
      {entries.map((e, i) => (
        <div key={i} className="space-y-2 rounded-lg border border-border bg-bg-subtle p-3">
          <div className="flex items-start gap-2">
            <div className="grid flex-1 grid-cols-[1fr_1fr_9rem] gap-2">
              <Input value={e.title} readOnly={readOnly} placeholder="Title" onChange={(ev) => set(i, { title: ev.target.value })} />
              <Input value={e.org} readOnly={readOnly} placeholder="Organisation" onChange={(ev) => set(i, { org: ev.target.value })} />
              <Input value={e.dates} readOnly={readOnly} placeholder="Dates" onChange={(ev) => set(i, { dates: ev.target.value })} />
            </div>
            {!readOnly && (
              <div className="flex">
                <IconAction label="Move up" onClick={() => onChange(move(entries, i, i - 1))} disabled={i === 0}>
                  <ArrowUp />
                </IconAction>
                <IconAction
                  label="Move down"
                  onClick={() => onChange(move(entries, i, i + 1))}
                  disabled={i === entries.length - 1}
                >
                  <ArrowDown />
                </IconAction>
                <IconAction label="Remove entry" onClick={() => onChange(entries.filter((_, j) => j !== i))}>
                  <Trash2 />
                </IconAction>
              </div>
            )}
          </div>
          {withBullets && (
            <BulletList bullets={e.bullets} readOnly={readOnly} onChange={(bullets) => set(i, { bullets })} />
          )}
        </div>
      ))}
      {!readOnly && (
        <Button size="sm" variant="ghost" onClick={() => onChange([...entries, { ...empty }])}>
          <Plus />
          Add entry
        </Button>
      )}
    </div>
  )
}

const EMPTY_ENTRY: CVEntry = { title: '', org: '', location: '', dates: '', bullets: [''] }

export function CVEditor({
  content,
  onChange,
  readOnly,
}: {
  content: CVContent
  onChange: Update
  readOnly: boolean
}) {
  const set = (patch: Partial<CVContent>) => onChange({ ...content, ...patch })
  return (
    <div>
      <Group title="Header">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label>Name</Label>
            <Input value={content.name} readOnly={readOnly} onChange={(e) => set({ name: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Headline</Label>
            <Input value={content.headline} readOnly={readOnly} onChange={(e) => set({ headline: e.target.value })} />
          </div>
        </div>
        <div className="space-y-1">
          <Label>Contact line (comma separated)</Label>
          <Input
            value={content.contact.join(', ')}
            readOnly={readOnly}
            onChange={(e) => set({ contact: e.target.value.split(',').map((s) => s.trimStart()) })}
          />
        </div>
      </Group>
      <Group title="Summary">
        <Textarea
          value={content.summary}
          readOnly={readOnly}
          onChange={(e) => set({ summary: e.target.value })}
          className="field-sizing-content"
        />
      </Group>
      <Group title="Experience">
        <EntryList
          entries={content.experience}
          readOnly={readOnly}
          empty={EMPTY_ENTRY}
          onChange={(experience) => set({ experience })}
        />
      </Group>
      <Group title="Projects">
        <EntryList
          entries={content.projects}
          readOnly={readOnly}
          empty={EMPTY_ENTRY}
          onChange={(projects) => set({ projects })}
        />
      </Group>
      <Group title="Skills">
        <div className="space-y-2">
          {content.skills.map((s, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input
                value={s.group}
                readOnly={readOnly}
                className="w-48"
                placeholder="Group"
                onChange={(e) =>
                  set({ skills: content.skills.map((x, j) => (j === i ? { ...x, group: e.target.value } : x)) })
                }
              />
              <Input
                value={s.items.join(', ')}
                readOnly={readOnly}
                placeholder="Comma-separated skills"
                onChange={(e) =>
                  set({
                    skills: content.skills.map((x, j) =>
                      j === i ? { ...x, items: e.target.value.split(',').map((v) => v.trimStart()) } : x,
                    ),
                  })
                }
              />
              {!readOnly && (
                <IconAction label="Remove group" onClick={() => set({ skills: content.skills.filter((_, j) => j !== i) })}>
                  <Trash2 />
                </IconAction>
              )}
            </div>
          ))}
          {!readOnly && (
            <Button size="sm" variant="ghost" onClick={() => set({ skills: [...content.skills, { group: '', items: [] }] })}>
              <Plus />
              Add skill group
            </Button>
          )}
        </div>
      </Group>
      <Group title="Education">
        <EntryList
          entries={content.education}
          readOnly={readOnly}
          withBullets={false}
          empty={{ ...EMPTY_ENTRY, bullets: [] }}
          onChange={(education) => set({ education })}
        />
      </Group>
    </div>
  )
}
