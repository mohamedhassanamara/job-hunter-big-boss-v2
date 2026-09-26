import { CircleHelp, Radar, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Tooltip } from '@/components/ui/tooltip'
import { useDiscoveryAction } from '@/hooks/useDiscoveryAction'
import { ThemeToggle } from './ThemeToggle'

export function TopBar({ onSearch, onHelp }: { onSearch: () => void; onHelp: () => void }) {
  const discovery = useDiscoveryAction()
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
            <Radar className={discovery.pending ? 'animate-pulse' : undefined} />
            Run discovery
          </Button>
        </Tooltip>
        <ThemeToggle />
        <Tooltip content={<span className="flex items-center gap-1.5">Keyboard shortcuts <Kbd>?</Kbd></span>}>
          <Button variant="ghost" size="icon" onClick={onHelp} aria-label="Keyboard shortcuts">
            <CircleHelp />
          </Button>
        </Tooltip>
      </div>
    </header>
  )
}
