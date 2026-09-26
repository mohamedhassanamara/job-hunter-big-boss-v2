import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Kbd } from '@/components/ui/kbd'

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
  {
    title: 'Go to',
    items: [
      [['G', 'T'], 'Today'],
      [['G', 'D'], 'Discover'],
      [['G', 'P'], 'Pipeline'],
      [['G', 'O'], 'Outreach'],
      [['G', 'C'], 'Contacts'],
      [['G', 'E'], 'Experience'],
      [['G', 'S'], 'Settings'],
    ],
  },
  {
    title: 'Lists',
    items: [
      [['J'], 'Next item'],
      [['K'], 'Previous item'],
      [['Enter'], 'Open'],
      [['S'], 'Shortlist'],
      [['D'], 'Dismiss (undo in toast)'],
    ],
  },
  {
    title: 'Outreach review',
    items: [
      [['A'], 'Approve draft'],
      [['R'], 'Reject draft'],
    ],
  },
]

export function ShortcutsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Keyboard shortcuts" className="max-w-2xl p-0">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-md font-semibold tracking-tight">Keyboard shortcuts</h2>
          <p className="text-sm text-fg-muted">Shortcuts are paused while you type in a field.</p>
        </div>
        <div className="grid grid-cols-2 gap-x-8 gap-y-5 px-5 py-4">
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
