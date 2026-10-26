import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Kbd } from '@/components/ui/kbd'
import { ALL_NAV } from './nav'

/** Go-to keys come from the sidebar's own list, so this dialog can't drift from the real keys. */
const GO_TO: [string[], string][] = ALL_NAV.map((item) => [['G', item.shortcut.toUpperCase()], item.label])

const GROUPS: { title: string; items: [string[], string][] }[] = [
  {
    title: 'Global',
    items: [
      [['⌘', 'K'], 'Command palette'],
      [['/'], 'Focus search or filter'],
      [['?'], 'Show shortcuts'],
      [['Esc'], 'Close panel or dialog'],
    ],
  },
  { title: 'Go to', items: GO_TO },
  {
    title: 'Lists (Discover, Pipeline table)',
    items: [
      [['J'], 'Next item'],
      [['K'], 'Previous item'],
      [['Enter'], 'Open'],
      [['S'], 'Shortlist'],
      [['D'], 'Dismiss (undo in toast)'],
      [['1', '2', '3'], 'Label good / maybe / no (Discover)'],
    ],
  },
  {
    title: 'Review CVs',
    items: [
      [['J', 'K'], 'Move'],
      [['A'], 'Approve, then the next CV'],
      [['R'], 'Regenerate (feedback optional)'],
      [['E'], 'Edit the summary'],
      [['S'], 'Skip'],
    ],
  },
  {
    title: 'CV Studio',
    items: [[['A'], 'Approve (when the checks pass)']],
  },
  {
    title: 'Outreach: review emails',
    items: [
      [['A'], 'Approve (and add to the queue)'],
      [['R'], 'Reject draft'],
    ],
  },
  {
    title: 'Outreach: queue',
    items: [
      [['S'], 'Start sending'],
      [['P'], 'Pause'],
    ],
  },
  {
    title: 'Applications: ready to apply',
    items: [
      [['O'], 'Open listing + CV (+ letter)'],
      [['A'], 'Mark applied'],
      [['Enter'], 'Confirm (opens the next listing)'],
    ],
  },
  {
    title: 'Contacts to get',
    items: [
      [['V'], 'Still there'],
      [['L'], 'Left'],
      [['E'], 'Edit'],
      [['P'], 'Paste box'],
      [['N'], 'Nobody found'],
      [['X'], 'Never look up'],
    ],
  },
  { title: 'Job page', items: [[['C'], 'Ask Copilot about this job']] },
]

export function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Keyboard shortcuts" className="max-w-2xl p-0">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-md font-semibold tracking-tight">Keyboard shortcuts</h2>
          <p className="text-sm text-fg-muted">Shortcuts are paused while you type in a field.</p>
        </div>
        <div className="grid max-h-[70vh] grid-cols-2 gap-x-8 gap-y-5 overflow-y-auto px-5 py-4">
          {GROUPS.map((g) => (
            <div key={g.title}>
              <h3 className="mb-2 text-xs font-medium text-fg-subtle">{g.title}</h3>
              <ul className="space-y-1.5">
                {g.items.map(([keys, label]) => (
                  <li key={label} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-fg-muted">{label}</span>
                    <span className="flex gap-1">
                      {keys.map((k) => (
                        <Kbd key={k}>{k}</Kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
