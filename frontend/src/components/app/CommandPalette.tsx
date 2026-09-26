import { Command } from 'cmdk'
import {
  Briefcase,
  Compass,
  Building2,
  CornerDownLeft,
  Moon,
  Pause,
  Play,
  Plus,
  Radar,
  Search,
  Sun,
  UserRound,
} from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Kbd } from '@/components/ui/kbd'
import { useQueueControl, useSearch, useToday } from '@/lib/queries/workflow'
import { cn } from '@/lib/utils'
import { ALL_NAV } from './nav'
import { useTheme } from './theme'
import { useDiscoveryAction } from '@/hooks/useDiscoveryAction'
import { TOUR_LIST } from '@/features/tours/tours'
import { useTour } from './tour/tour-context'

const itemClass =
  'flex h-9 cursor-default items-center gap-2.5 rounded-md px-2.5 text-sm text-fg select-none data-[selected=true]:bg-surface-hover [&_svg]:size-4 [&_svg]:text-fg-subtle [&_svg]:shrink-0'
const groupClass =
  '[&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-2xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-fg-subtle'

const HIT_ICON = { job: Briefcase, company: Building2, contact: UserRound }

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const { resolved, setPreference } = useTheme()
  const search = useSearch(query)
  const today = useToday()
  const queueControl = useQueueControl()
  const discovery = useDiscoveryAction()
  const tours = useTour()

  const close = () => {
    onOpenChange(false)
    setQuery('')
  }
  const go = (to: string) => {
    close()
    navigate(to)
  }

  const q = query.trim().toLowerCase()
  const matches = (label: string) => !q || label.toLowerCase().includes(q)
  const queueRunning = today.data?.queue.status === 'running'

  const actions = [
    {
      id: 'discovery',
      label: 'Run discovery now',
      icon: Radar,
      run: () => discovery.trigger(),
    },
    {
      id: 'queue',
      label: queueRunning ? 'Pause send queue' : 'Resume send queue',
      icon: queueRunning ? Pause : Play,
      run: () =>
        queueControl.mutate(queueRunning ? 'pause' : 'resume', {
          onSuccess: (qd) => toast.success(qd.status === 'running' ? 'Queue resumed' : 'Queue paused'),
        }),
    },
    {
      id: 'experience',
      label: 'Add experience item',
      icon: Plus,
      run: () => navigate('/experience?new=1'),
    },
    {
      id: 'theme',
      label: resolved === 'dark' ? 'Switch to light theme' : 'Switch to dark theme',
      icon: resolved === 'dark' ? Sun : Moon,
      run: () => setPreference(resolved === 'dark' ? 'light' : 'dark'),
    },
    ...TOUR_LIST.map((t) => ({
      id: `tour-${t.id}`,
      label: `Tour: ${t.title} (sample data)`,
      icon: Compass,
      run: () => tours.start(t.id),
    })),
  ].filter((a) => matches(a.label))

  const nav = ALL_NAV.filter((n) => matches(`Go to ${n.label}`))
  const hits = q.length > 1 ? (search.data?.hits ?? []) : []

  return (
    <Dialog open={open} onOpenChange={(o) => (o ? onOpenChange(true) : close())}>
      <DialogContent title="Command palette" className="max-w-xl overflow-hidden p-0" hideClose>
        <Command shouldFilter={false} loop className="flex flex-col">
          <div className="flex h-12 items-center gap-2.5 border-b border-border px-4">
            <Search className="size-4 text-fg-subtle" />
            <Command.Input
              value={query}
              onValueChange={setQuery}
              autoFocus
              placeholder="Search jobs, companies, contacts, or type a command…"
              className="h-full flex-1 bg-transparent text-base text-fg outline-none placeholder:text-fg-subtle"
            />
            <Kbd>Esc</Kbd>
          </div>
          <Command.List className="max-h-[min(420px,60vh)] overflow-y-auto p-1.5">
            <Command.Empty className="px-3 py-8 text-center text-sm text-fg-muted">
              {search.isFetching ? 'Searching…' : `No results for “${query}”`}
            </Command.Empty>
            {hits.length > 0 && (
              <Command.Group heading="Results" className={groupClass}>
                {hits.map((h) => {
                  const Icon = HIT_ICON[h.kind]
                  return (
                    <Command.Item
                      key={`${h.kind}-${h.id}`}
                      value={`${h.kind}-${h.id}`}
                      onSelect={() => go(h.href)}
                      className={itemClass}
                    >
                      <Icon />
                      <span className="truncate">{h.title}</span>
                      <span className="truncate text-fg-subtle">{h.subtitle}</span>
                    </Command.Item>
                  )
                })}
              </Command.Group>
            )}
            {actions.length > 0 && (
              <Command.Group heading="Actions" className={groupClass}>
                {actions.map((a) => (
                  <Command.Item
                    key={a.id}
                    value={a.id}
                    onSelect={() => {
                      close()
                      a.run()
                    }}
                    className={itemClass}
                  >
                    <a.icon />
                    {a.label}
                  </Command.Item>
                ))}
              </Command.Group>
            )}
            {nav.length > 0 && (
              <Command.Group heading="Navigate" className={groupClass}>
                {nav.map((n) => (
                  <Command.Item
                    key={n.to}
                    value={`nav-${n.to}`}
                    onSelect={() => go(n.to)}
                    className={itemClass}
                  >
                    <n.icon />
                    <span className="flex-1">Go to {n.label}</span>
                    <span className="flex gap-0.5">
                      <Kbd>G</Kbd>
                      <Kbd>{n.shortcut.toUpperCase()}</Kbd>
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}
          </Command.List>
          <div className={cn('flex h-9 items-center gap-3 border-t border-border px-4 text-2xs text-fg-subtle')}>
            <span className="flex items-center gap-1">
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> navigate
            </span>
            <span className="flex items-center gap-1">
              <Kbd>
                <CornerDownLeft className="size-2.5" />
              </Kbd>
              open
            </span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  )
}
