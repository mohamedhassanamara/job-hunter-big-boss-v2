import { CircleHelp, Compass, Keyboard, LoaderCircle, Radar, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Kbd } from '@/components/ui/kbd'
import { Tooltip } from '@/components/ui/tooltip'
import { useDiscoveryAction } from '@/hooks/useDiscoveryAction'
import { ThemeToggle } from './ThemeToggle'
import { TOUR_LIST } from '@/features/tours/tours'
import { useTour } from './tour/tour-context'

export function TopBar({ onSearch, onHelp }: { onSearch: () => void; onHelp: () => void }) {
  const discovery = useDiscoveryAction()
  const tours = useTour()
  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border bg-bg px-4">
      <button
        onClick={onSearch}
        className="flex h-8 w-full max-w-md items-center gap-2 rounded-md border border-border bg-surface px-2.5 text-sm text-fg-subtle shadow-sm transition-colors duration-120 hover:border-border-strong hover:text-fg-muted"
      >
        <Search className="size-4" />
        <span className="flex-1 text-left">Search jobs, companies, contacts…</span>
        <span className="flex gap-0.5">
          <Kbd>⌘</Kbd>
          <Kbd>K</Kbd>
        </span>
      </button>
      <div className="ml-auto flex items-center gap-1">
        <Tooltip content="Pull new jobs from all enabled sources (mock in phase 0)">
          <Button variant="ghost" size="sm" onClick={discovery.trigger} disabled={discovery.pending}>
            {discovery.pending ? <LoaderCircle className="animate-spin" /> : <Radar />}
            {discovery.pending ? 'Discovering…' : 'Run discovery'}
          </Button>
        </Tooltip>
        <ThemeToggle />
        <DropdownMenu>
          <Tooltip content="Help, shortcuts and guided tours">
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Help" data-tour-help>
                <CircleHelp />
              </Button>
            </DropdownMenuTrigger>
          </Tooltip>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuItem onSelect={onHelp}>
              <Keyboard />
              <span className="flex-1">Keyboard shortcuts</span>
              <Kbd>?</Kbd>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Guided tours · sample data</DropdownMenuLabel>
            {TOUR_LIST.map((t) => (
              <DropdownMenuItem key={t.id} onSelect={() => tours.start(t.id)} disabled={tours.starting}>
                <Compass />
                <span className="flex-1">{t.title}</span>
                <span className="text-xs text-fg-subtle">{t.steps.length} steps</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
