import {
  Compass,
  Inbox,
  Layers,
  type LucideIcon,
  Send,
  Settings,
  SquareKanban,
  Users,
} from 'lucide-react'
import type { NavCounts } from '@/lib/types'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  shortcut: string // second key of the "g x" sequence
  count?: keyof NavCounts
}

export const NAV_MAIN: NavItem[] = [
  { to: '/', label: 'Today', icon: Inbox, shortcut: 't' },
  { to: '/discover', label: 'Discover', icon: Compass, shortcut: 'd', count: 'discover_new' },
  { to: '/pipeline', label: 'Pipeline', icon: SquareKanban, shortcut: 'p', count: 'pipeline_active' },
  { to: '/outreach', label: 'Outreach', icon: Send, shortcut: 'o', count: 'outreach_review' },
]

export const NAV_LIBRARY: NavItem[] = [
  { to: '/contacts', label: 'Contacts', icon: Users, shortcut: 'c' },
  { to: '/experience', label: 'Experience', icon: Layers, shortcut: 'e' },
]

export const NAV_SETTINGS: NavItem = {
  to: '/settings',
  label: 'Settings',
  icon: Settings,
  shortcut: 's',
}

export const ALL_NAV = [...NAV_MAIN, ...NAV_LIBRARY, NAV_SETTINGS]
