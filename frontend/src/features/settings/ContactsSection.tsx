import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { TagInput } from '@/components/app/TagInput'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useSaveSetting } from '@/lib/queries/library'
import type { RoleGroup, SettingsView } from '@/lib/types'
import { DoNotContactCard } from './DoNotContactCard'
import { ProvidersCard } from './ProvidersCard'
import { Card, Field, SaveBar } from './sections'

const EXCLUDE_DEFAULT = ['business development', 'sales', 'account']
const SMALL_DEFAULT = ['CTO', 'Founder / CEO', 'VP / Head of Engineering', 'Head of Data / AI / ML', 'Engineering Manager', 'Tech Lead', 'HR / Talent']
const LARGE_DEFAULT = ['HR / Talent', 'Engineering Manager', 'CTO', 'VP / Head of Engineering', 'Head of Data / AI / ML', 'Tech Lead', 'Founder / CEO']

/** The saved order, limited to existing groups, with any new group appended. */
function normalizeOrder(order: string[] | undefined, groups: RoleGroup[], fallback: string[]): string[] {
  const labels = groups.map((g) => g.label)
  const kept = (order ?? fallback).filter((l) => labels.includes(l))
  return [...kept, ...labels.filter((l) => !kept.includes(l))]
}

function OrderList({ title, order, onChange }: { title: string; order: string[]; onChange: (o: string[]) => void }) {
  const move = (i: number, d: -1 | 1) => {
    const next = [...order]
    ;[next[i], next[i + d]] = [next[i + d], next[i]]
    onChange(next)
  }
  return (
    <div className="flex-1 rounded-lg border border-border bg-surface">
      <p className="border-b border-border px-3 py-2 text-xs font-medium text-fg-subtle">{title}</p>
      <ol>
        {order.map((label, i) => (
          <li key={label} className="flex items-center gap-2 border-b border-border px-3 py-1.5 text-sm last:border-b-0">
            <span className="w-4 text-right text-xs text-fg-subtle tabular-nums">{i + 1}</span>
            <span className="flex-1 truncate">{label}</span>
            <Button size="icon-sm" variant="ghost" aria-label={`Move ${label} up`} disabled={i === 0} onClick={() => move(i, -1)}>
              <ArrowUp />
            </Button>
            <Button size="icon-sm" variant="ghost" aria-label={`Move ${label} down`} disabled={i === order.length - 1} onClick={() => move(i, 1)}>
              <ArrowDown />
            </Button>
          </li>
        ))}
      </ol>
    </div>
  )
}

/** Who to write to first at a company (by size), the Apollo extension daily limit, and how long a verification lasts. */
export function ContactsSection({ settings }: { settings: SettingsView }) {
  const saved = settings.values.contacts ?? {}
  const initialRanking = ((saved.role_ranking as RoleGroup[] | undefined) ?? []).map((g) => ({ ...g }))
  const initialSmall = normalizeOrder(saved.small_order as string[] | undefined, initialRanking, SMALL_DEFAULT)
  const initialLarge = normalizeOrder(saved.large_order as string[] | undefined, initialRanking, LARGE_DEFAULT)
  const initialThreshold = Number(saved.small_company_threshold ?? 200)
  const initialCap = Number(settings.values.lookup?.daily_cap ?? 10)
  const initialVerify = Number(saved.verify_days ?? 30)
  const initialExclude = (saved.exclude_keywords as string[] | undefined) ?? EXCLUDE_DEFAULT
  const [ranking, setRanking] = useState<RoleGroup[]>(initialRanking)
  const [small, setSmall] = useState(initialSmall)
  const [large, setLarge] = useState(initialLarge)
  const [threshold, setThreshold] = useState(initialThreshold)
  const [cap, setCap] = useState(initialCap)
  const [verifyDays, setVerifyDays] = useState(initialVerify)
  const [exclude, setExclude] = useState(initialExclude)
  const save = useSaveSetting()
  const rankingDirty =
    JSON.stringify([ranking, small, large, threshold, verifyDays, exclude]) !== JSON.stringify([initialRanking, initialSmall, initialLarge, initialThreshold, initialVerify, initialExclude])
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
    if (!Number.isInteger(threshold) || threshold < 1) {
      toast.error('The size threshold must be a number of employees')
      return
    }
    if (!Number.isInteger(cap) || cap < 1 || cap > 100) {
      toast.error('The daily limit must be between 1 and 100')
      return
    }
    if (!Number.isInteger(verifyDays) || verifyDays < 1 || verifyDays > 365) {
      toast.error('Verification lasts between 1 and 365 days')
      return
    }
    try {
      if (rankingDirty)
        await save.mutateAsync({
          key: 'contacts',
          value: {
            role_ranking: ranking,
            small_order: normalizeOrder(small, ranking, SMALL_DEFAULT),
            large_order: normalizeOrder(large, ranking, LARGE_DEFAULT),
            small_company_threshold: threshold,
            verify_days: verifyDays,
            exclude_keywords: exclude,
          },
        })
      if (capDirty) await save.mutateAsync({ key: 'lookup', value: { daily_cap: cap } })
      toast.success('Contacts settings saved', { description: rankingDirty ? 'Every contact was re-ranked and jobs re-matched.' : undefined })
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <div className="space-y-6">
    <Card
      title="Contacts"
      description="The order decides who each job's email goes to: the first group with someone at the company wins, in the order for its size. Keywords match whole words in the title, ignoring accents and case."
      footer={
        <SaveBar
          dirty={rankingDirty || capDirty}
          saving={save.isPending}
          onReset={() => {
            setRanking(initialRanking)
            setSmall(initialSmall)
            setLarge(initialLarge)
            setThreshold(initialThreshold)
            setExclude(initialExclude)
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
      <Field label="Never match titles containing" hint="Whole words or phrases, in every group: “Business Development Manager” is not an engineering manager">
        <div data-tour="settings-contacts-exclude">
          <TagInput tags={exclude} onChange={setExclude} placeholder="business development, sales, account… (Enter to add)" />
        </div>
      </Field>
      <Field label="Small company" hint="Uses the small-company order">
        <div className="flex items-center gap-2 text-sm">
          Up to
          <Input type="number" min={1} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} className="w-24" aria-label="Small company threshold" />
          employees. An “under N” size (Apollo lists) counts as small when N is at most this; unknown size uses the large order.
        </div>
      </Field>
      <div data-tour="settings-contacts-orders" className="flex gap-3">
        <OrderList title={`Small companies (up to ${threshold})`} order={normalizeOrder(small, ranking, SMALL_DEFAULT)} onChange={setSmall} />
        <OrderList title="Large or unknown size" order={normalizeOrder(large, ranking, LARGE_DEFAULT)} onChange={setLarge} />
      </div>
      <Field label="Apollo extension daily limit" hint="Contacts you can reveal per day: the Get contact counter warns near it (it never blocks)">
        <Input type="number" min={1} max={100} value={cap} onChange={(e) => setCap(Number(e.target.value))} className="w-24" aria-label="Apollo extension daily limit" />
      </Field>
      <Field label="Verification lasts" hint="After this, a contact is verified again before a new email">
        <div className="flex items-center gap-2 text-sm">
          <Input type="number" min={1} max={365} value={verifyDays} onChange={(e) => setVerifyDays(Number(e.target.value))} className="w-24" aria-label="Verification lasts (days)" />
          days
        </div>
      </Field>
    </Card>
    <DoNotContactCard />
    <ProvidersCard settings={settings} />
    </div>
  )
}
