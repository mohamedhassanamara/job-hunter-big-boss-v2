import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Tooltip } from '@/components/ui/tooltip'
import { useSaveSetting } from '@/lib/queries/library'
import { useSources } from '@/lib/queries/workflow'
import type { CompanyBoard } from '@/lib/types'
import { cn } from '@/lib/utils'

const ATS_OPTIONS = [
  { value: 'greenhouse', label: 'Greenhouse' },
  { value: 'lever', label: 'Lever' },
  { value: 'ashby', label: 'Ashby' },
  { value: 'workable', label: 'Workable' },
  { value: 'smartrecruiters', label: 'SmartRecruiters' },
]

const TOKEN_HINT: Record<CompanyBoard['ats'], string> = {
  greenhouse: 'boards.greenhouse.io/<token>',
  lever: 'jobs.lever.co/<token>',
  ashby: 'jobs.ashbyhq.com/<token>',
  workable: 'apply.workable.com/<token>',
  smartrecruiters: 'careers.smartrecruiters.com/<token>',
}

const label = (b: CompanyBoard) => `${b.company || b.token} (${b.ats})`

/** Editable list of company job boards (app_setting.company_boards), with each board's result
 * from the last run so a wrong token (0 jobs) or a moved board (error) is easy to spot. */
export function BoardsEditor({
  boards,
  results,
}: {
  boards: CompanyBoard[]
  results: Record<string, string | number>
}) {
  const [rows, setRows] = useState<CompanyBoard[]>(boards)
  const save = useSaveSetting()
  const sources = useSources()
  const dirty = JSON.stringify(rows) !== JSON.stringify(boards)
  const set = (i: number, patch: Partial<CompanyBoard>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  const onSave = () =>
    save.mutate(
      { key: 'company_boards', value: { boards: rows.filter((r) => r.token.trim()) } },
      {
        onSuccess: () => {
          toast.success('Company boards saved')
          void sources.refetch()
        },
        onError: (e) => toast.error(e.message),
      },
    )

  return (
    <div className="rounded-lg border border-border bg-bg-subtle p-3">
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <p className="text-xs font-medium text-fg">Companies ({rows.length})</p>
        <p className="text-2xs text-fg-subtle">The token is the company's id in its careers-page URL.</p>
      </div>
      <div className="space-y-1.5">
        {rows.map((row, i) => {
          const result = results[label(row)]
          const bad = typeof result === 'string' || result === 0
          return (
            <div key={i} className="grid grid-cols-[150px_minmax(0,1fr)_minmax(0,1fr)_96px_28px] items-center gap-2">
              <Select value={row.ats} onValueChange={(v) => set(i, { ats: v as CompanyBoard['ats'] })} options={ATS_OPTIONS} />
              <Input value={row.token} onChange={(e) => set(i, { token: e.target.value })} placeholder={TOKEN_HINT[row.ats]} aria-label="Board token" />
              <Input value={row.company} onChange={(e) => set(i, { company: e.target.value })} placeholder="Company name" aria-label="Company name" />
              <Tooltip content={typeof result === 'string' ? result : result === 0 ? 'The board answered with no jobs: check the token' : null}>
                <span className={cn('truncate text-xs tabular-nums', bad ? 'text-warning-fg' : 'text-fg-muted')}>
                  {result === undefined ? '–' : typeof result === 'string' ? 'Error' : `${result} jobs`}
                </span>
              </Tooltip>
              <Button variant="ghost" size="icon-sm" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label={`Remove ${label(row)}`}>
                <Trash2 />
              </Button>
            </div>
          )
        })}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setRows([...rows, { ats: 'greenhouse', token: '', company: '' }])}>
          <Plus /> Add company
        </Button>
        <div className="flex-1" />
        {dirty && (
          <Button variant="ghost" size="sm" onClick={() => setRows(boards)}>
            Discard
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={onSave} disabled={!dirty || save.isPending}>
          Save companies
        </Button>
      </div>
    </div>
  )
}
