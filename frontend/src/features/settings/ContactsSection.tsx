import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { TagInput } from '@/components/app/TagInput'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useSaveSetting } from '@/lib/queries/library'
import type { RoleGroup, SettingsView } from '@/lib/types'
import { Card, Field, SaveBar } from './sections'

/** Who to write to first at a company, and the daily cap of manual Apollo lookups. */
export function ContactsSection({ settings }: { settings: SettingsView }) {
  const initialRanking = ((settings.values.contacts?.role_ranking as RoleGroup[] | undefined) ?? []).map((g) => ({ ...g }))
  const initialCap = Number(settings.values.lookup?.daily_cap ?? 10)
  const [ranking, setRanking] = useState<RoleGroup[]>(initialRanking)
  const [cap, setCap] = useState(initialCap)
  const save = useSaveSetting()
  const rankingDirty = JSON.stringify(ranking) !== JSON.stringify(initialRanking)
  const capDirty = cap !== initialCap
  const invalid = ranking.length === 0 || ranking.some((g) => !g.label.trim() || g.keywords.length === 0)

  const update = (i: number, patch: Partial<RoleGroup>) => setRanking((r) => r.map((g, j) => (j === i ? { ...g, ...patch } : g)))
  const move = (i: number, d: -1 | 1) =>
    setRanking((r) => {
      const next = [...r]
      ;[next[i], next[i + d]] = [next[i + d], next[i]]
      return next
    })

  const onSave = async () => {
    if (invalid) {
      toast.error('Every group needs a label and at least one keyword')
      return
    }
    if (!Number.isInteger(cap) || cap < 1 || cap > 100) {
      toast.error('The daily cap must be between 1 and 100')
      return
    }
    try {
      if (rankingDirty) await save.mutateAsync({ key: 'contacts', value: { role_ranking: ranking } })
      if (capDirty) await save.mutateAsync({ key: 'lookup', value: { daily_cap: cap } })
      toast.success('Contacts settings saved', { description: rankingDirty ? 'Every contact was re-ranked and jobs re-matched.' : undefined })
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <Card
      title="Contacts"
      description="The order decides who each job's email goes to: the first group with someone at the company wins. Keywords match whole words in the title, ignoring accents and case."
      footer={
        <SaveBar
          dirty={rankingDirty || capDirty}
          saving={save.isPending}
          onReset={() => {
            setRanking(initialRanking)
            setCap(initialCap)
          }}
          onSave={() => void onSave()}
        />
      }
    >
      <div data-tour="settings-contacts-ranking" className="space-y-2">
        {ranking.map((g, i) => (
          <div key={i} className="flex items-start gap-2 rounded-lg border border-border bg-surface p-3">
            <span className="mt-1.5 w-5 text-right text-xs font-semibold text-fg-subtle tabular-nums">{i + 1}</span>
            <div className="min-w-0 flex-1 space-y-2">
              <Input value={g.label} onChange={(e) => update(i, { label: e.target.value })} aria-label={`Group ${i + 1} label`} className="h-7 w-64" />
              <TagInput tags={g.keywords} onChange={(keywords) => update(i, { keywords })} placeholder="cto, head of engineering… (Enter to add)" />
            </div>
            <div className="flex flex-col gap-0.5">
              <Button size="icon-sm" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                <ArrowUp />
              </Button>
              <Button size="icon-sm" variant="ghost" aria-label="Move down" disabled={i === ranking.length - 1} onClick={() => move(i, 1)}>
                <ArrowDown />
              </Button>
              <Button size="icon-sm" variant="ghost" aria-label="Remove group" onClick={() => setRanking((r) => r.filter((_, j) => j !== i))}>
                <Trash2 />
              </Button>
            </div>
          </div>
        ))}
        <Button size="sm" variant="ghost" onClick={() => setRanking((r) => [...r, { label: 'New group', keywords: [] }])}>
          <Plus />
          Add group
        </Button>
        <p className="text-xs text-fg-subtle">Titles matching no group rank last. Ties: someone with an email, then the most recently imported.</p>
      </div>
      <Field label="Apollo lookups per day" hint="The extension's free quota">
        <Input type="number" min={1} max={100} value={cap} onChange={(e) => setCap(Number(e.target.value))} className="w-24" />
      </Field>
    </Card>
  )
}
