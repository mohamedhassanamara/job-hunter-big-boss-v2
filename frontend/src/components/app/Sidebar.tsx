import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { NavLink } from 'react-router'
import { Kbd } from '@/components/ui/kbd'
import { Tooltip } from '@/components/ui/tooltip'
import { useNavCounts } from '@/lib/queries/workflow'
import { cn } from '@/lib/utils'
import { NAV_LIBRARY, NAV_MAIN, NAV_SETTINGS, type NavItem } from './nav'

function Logo({ collapsed }: { collapsed: boolean }) {
  return (
    <div className={cn('flex h-12 items-center gap-2', collapsed ? 'justify-center' : 'px-3')}>
      <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-fg">
        <svg viewBox="0 0 16 16" className="size-3.5" fill="none" aria-hidden>
          <path d="M3 8.5 6.5 12 13 4" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      {!collapsed && <span className="text-sm font-semibold tracking-tight">Job Hunter</span>}
    </div>
  )
}

function NavEntry({ item, collapsed, count }: { item: NavItem; collapsed: boolean; count?: number }) {
  const Icon = item.icon
  const link = (
    <NavLink
      to={item.to}
      end={item.to === '/'}
      className={({ isActive }) =>
        cn(
          'group flex h-8 items-center gap-2.5 rounded-md text-sm font-medium transition-colors duration-120',
          collapsed ? 'justify-center' : 'px-2',
          isActive
            ? 'bg-surface-selected text-fg'
            : 'text-fg-muted hover:bg-surface-hover hover:text-fg',
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon
            className={cn('size-4 shrink-0', isActive ? 'text-primary' : 'text-fg-subtle group-hover:text-fg-muted')}
            strokeWidth={1.75}
          />
          {!collapsed && <span className="flex-1 truncate">{item.label}</span>}
          {!collapsed && !!count && (
            <span className="text-xs font-medium text-fg-subtle tabular-nums">{count}</span>
          )}
        </>
      )}
    </NavLink>
  )
  return collapsed ? (
    <Tooltip
      side="right"
      content={
        <span className="flex items-center gap-2">
          {item.label}
          {!!count && <span className="text-fg-muted tabular-nums">{count}</span>}
          <span className="flex gap-0.5">
            <Kbd>G</Kbd>
            <Kbd>{item.shortcut.toUpperCase()}</Kbd>
          </span>
        </span>
      }
    >
      {link}
    </Tooltip>
  ) : (
    <Tooltip
      side="right"
      content={
        <span className="flex items-center gap-1">
          Go to {item.label.toLowerCase()} <Kbd>G</Kbd>
          <Kbd>{item.shortcut.toUpperCase()}</Kbd>
        </span>
      }
    >
      {link}
    </Tooltip>
  )
}

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean
  onToggle: () => void
}) {
  const { data: counts } = useNavCounts()
  return (
    <aside
      className={cn(
        'flex h-full shrink-0 flex-col border-r border-border bg-bg-subtle transition-[width] duration-200',
        collapsed ? 'w-[52px]' : 'w-[232px]',
      )}
    >
      <Logo collapsed={collapsed} />
      <nav className={cn('flex flex-1 flex-col gap-4 py-2', collapsed ? 'px-2' : 'px-2.5')}>
        <div className="flex flex-col gap-0.5">
          {NAV_MAIN.map((item) => (
            <NavEntry
              key={item.to}
              item={item}
              collapsed={collapsed}
              count={item.count ? counts?.[item.count] : undefined}
            />
          ))}
        </div>
        <div className="flex flex-col gap-0.5">
          {!collapsed && (
            <p className="px-2 pb-1 text-2xs font-medium text-fg-subtle">Library</p>
          )}
          {NAV_LIBRARY.map((item) => (
            <NavEntry key={item.to} item={item} collapsed={collapsed} />
          ))}
        </div>
      </nav>
      <div className={cn('flex flex-col gap-0.5 border-t border-border py-2', collapsed ? 'px-2' : 'px-2.5')}>
        <NavEntry item={NAV_SETTINGS} collapsed={collapsed} />
        <Tooltip side="right" content={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <button
            onClick={onToggle}
            className={cn(
              'flex h-8 items-center gap-2.5 rounded-md text-sm text-fg-subtle hover:bg-surface-hover hover:text-fg',
              collapsed ? 'justify-center' : 'px-2',
            )}
          >
            {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
            {!collapsed && <span>Collapse</span>}
          </button>
        </Tooltip>
      </div>
    </aside>
  )
}
