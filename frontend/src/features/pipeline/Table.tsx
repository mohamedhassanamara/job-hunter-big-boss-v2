import { ArrowDown, ArrowUp } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import { ContactTierBadge, FitBadge, RouteLabel, StageBadge } from '@/components/app/badges'
import { Tooltip } from '@/components/ui/tooltip'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { absoluteDate, relativeTime, STAGE_ORDER } from '@/lib/format'
import type { PipelineCard } from '@/lib/types'
import { cn } from '@/lib/utils'

type SortKey = 'title' | 'company' | 'stage' | 'fit' | 'updated'

const COLUMNS: { key: SortKey | null; label: string; className: string }[] = [
  { key: 'title', label: 'Job', className: 'w-auto' },
  { key: 'company', label: 'Company', className: 'w-44' },
  { key: 'stage', label: 'Stage', className: 'w-40' },
  { key: null, label: 'Route', className: 'w-32' },
  { key: 'fit', label: 'Fit', className: 'w-16' },
  { key: null, label: 'Contact', className: 'w-40' },
  { key: 'updated', label: 'In stage', className: 'w-28' },
]

function compare(a: PipelineCard, b: PipelineCard, key: SortKey) {
  switch (key) {
    case 'title':
      return a.title.localeCompare(b.title)
    case 'company':
      return a.company_name.localeCompare(b.company_name)
    case 'stage':
      return STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage)
    case 'fit':
      return (a.fit?.score ?? -1) - (b.fit?.score ?? -1)
    case 'updated':
      return a.stage_changed_at.localeCompare(b.stage_changed_at)
  }
}

export function Table({
  cards,
  onShortlist,
  onDismiss,
}: {
  cards: PipelineCard[]
  onShortlist: (c: PipelineCard) => void
  onDismiss: (c: PipelineCard) => void
}) {
  const navigate = useNavigate()
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'stage', dir: 1 })
  const [selected, setSelected] = useState<number | null>(null)

  const rows = useMemo(
    () => [...cards].sort((a, b) => compare(a, b, sort.key) * sort.dir || b.updated_at.localeCompare(a.updated_at)),
    [cards, sort],
  )
  const ids = useMemo(() => rows.map((r) => r.application_id), [rows])
  const byId = (id: number) => rows.find((r) => r.application_id === id)

  useListKeyboard({
    ids,
    selectedId: selected,
    onSelect: setSelected,
    onOpen: (id) => navigate(`/jobs/${byId(id)?.job_id}`),
    actions: {
      s: (id) => {
        const c = byId(id)
        if (c?.stage === 'new') onShortlist(c)
      },
      d: (id) => {
        const c = byId(id)
        if (c && c.stage !== 'closed') onDismiss(c)
      },
    },
  })

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: key === 'fit' || key === 'updated' ? -1 : 1 }))

  return (
    <div className="px-6 py-4">
      <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
        <table className="w-full table-fixed text-sm">
          <thead className="bg-bg-subtle">
            <tr className="border-b border-border">
              {COLUMNS.map((col) => (
                <th key={col.label} className={cn('h-9 px-3 text-left text-xs font-medium text-fg-muted', col.className)}>
                  {col.key ? (
                    <button
                      onClick={() => toggleSort(col.key!)}
                      className="inline-flex items-center gap-1 hover:text-fg"
                    >
                      {col.label}
                      {sort.key === col.key &&
                        (sort.dir === 1 ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
                    </button>
                  ) : (
                    col.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr
                key={c.application_id}
                data-row-id={c.application_id}
                onClick={() => navigate(`/jobs/${c.job_id}`)}
                onMouseEnter={() => setSelected(c.application_id)}
                className={cn(
                  'h-11 cursor-default border-b border-border transition-colors duration-120 last:border-b-0',
                  selected === c.application_id ? 'bg-surface-selected' : 'hover:bg-surface-hover',
                )}
              >
                <td className="truncate px-3 font-medium">{c.title}</td>
                <td className="truncate px-3 text-fg-muted">{c.company_name}</td>
                <td className="px-3">
                  <StageBadge stage={c.stage} label={c.stage_label} />
                </td>
                <td className="px-3">
                  <RouteLabel route={c.route} />
                </td>
                <td className="px-3">
                  <FitBadge fit={c.fit} size="sm" />
                </td>
                <td className="px-3">
                  <ContactTierBadge tier={c.contact_tier} />
                </td>
                <td className="px-3 text-xs text-fg-subtle tabular-nums">
                  <Tooltip content={absoluteDate(c.stage_changed_at)}>
                    <span>{relativeTime(c.stage_changed_at)}</span>
                  </Tooltip>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-fg-subtle">J/K to move · Enter to open · S shortlist · D dismiss</p>
    </div>
  )
}
