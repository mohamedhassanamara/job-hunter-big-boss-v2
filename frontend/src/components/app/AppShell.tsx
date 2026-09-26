import { useEffect, useState } from 'react'
import { Outlet, useNavigate } from 'react-router'
import { useHotkeys } from '@/hooks/useHotkeys'
import { CommandPalette } from './CommandPalette'
import { DiscoveryWatcher } from './DiscoveryWatcher'
import { ALL_NAV } from './nav'
import { ShortcutsDialog } from './ShortcutsDialog'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import { TourProvider } from './tour/TourProvider'
import { TourStrip } from './tour/TourStrip'

const COLLAPSE_KEY = 'jh-sidebar-collapsed'
const AUTO_COLLAPSE_QUERY = '(max-width: 1279px)'

function useSidebarCollapsed() {
  const [userPref, setUserPref] = useState<boolean | null>(() => {
    const v = localStorage.getItem(COLLAPSE_KEY)
    return v === null ? null : v === '1'
  })
  const [narrow, setNarrow] = useState(() => window.matchMedia(AUTO_COLLAPSE_QUERY).matches)
  useEffect(() => {
    const mq = window.matchMedia(AUTO_COLLAPSE_QUERY)
    const onChange = () => {
      setNarrow(mq.matches)
      setUserPref(null) // crossing the breakpoint resets to automatic behaviour
      localStorage.removeItem(COLLAPSE_KEY)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  const collapsed = userPref ?? narrow
  const toggle = () => {
    setUserPref(!collapsed)
    localStorage.setItem(COLLAPSE_KEY, !collapsed ? '1' : '0')
  }
  return { collapsed, toggle }
}

export function AppShell() {
  const navigate = useNavigate()
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const { collapsed, toggle } = useSidebarCollapsed()

  const goTo: Record<string, () => void> = {}
  for (const item of ALL_NAV) goTo[`g ${item.shortcut}`] = () => navigate(item.to)

  useHotkeys({ 'mod+k': () => setPaletteOpen((o) => !o) }, { allowInInputs: true, allowInOverlay: true })
  useHotkeys({
    ...goTo,
    '?': () => setHelpOpen(true),
    '/': () => {
      const pageSearch = document.querySelector<HTMLInputElement>('[data-page-search]')
      if (pageSearch) pageSearch.focus()
      else setPaletteOpen(true)
    },
  })

  return (
    <TourProvider>
    <div className="flex h-full min-w-[1024px]">
      <Sidebar collapsed={collapsed} onToggle={toggle} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TourStrip />
        <TopBar onSearch={() => setPaletteOpen(true)} onHelp={() => setHelpOpen(true)} />
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <ShortcutsDialog open={helpOpen} onOpenChange={setHelpOpen} />
      <DiscoveryWatcher />
    </div>
    </TourProvider>
  )
}
