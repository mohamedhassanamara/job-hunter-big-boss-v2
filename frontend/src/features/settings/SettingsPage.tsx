import { Bot, CalendarClock, Database, Mail, Radar, SlidersHorizontal } from 'lucide-react'
import { PageHeader } from '@/components/app/PageHeader'
import { ErrorState } from '@/components/app/states'
import { Skeleton } from '@/components/ui/skeleton'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useSearchProfile, useSettings } from '@/lib/queries/library'
import { cn } from '@/lib/utils'
import {
  DataSection,
  EmailSection,
  ModelsSection,
  ProfileSection,
  ScheduleSection,
} from './sections'
import { SourcesSection } from './SourcesSection'

const SECTIONS = [
  { id: 'profile', label: 'Search profile', icon: SlidersHorizontal },
  { id: 'sources', label: 'Sources', icon: Radar },
  { id: 'schedule', label: 'Schedule', icon: CalendarClock },
  { id: 'models', label: 'Models', icon: Bot },
  { id: 'email', label: 'Email', icon: Mail },
  { id: 'data', label: 'Data', icon: Database },
] as const

export default function SettingsPage() {
  const url = useSearchParamState()
  const section = url.get('section') ?? 'profile'
  const settings = useSettings()
  const profile = useSearchProfile()
  const error = settings.error ?? profile.error

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Settings" description="Search profile, sources, models and sending." />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex max-w-5xl gap-8 px-6 py-6">
          <nav className="w-48 shrink-0 space-y-0.5" aria-label="Settings sections">
            {SECTIONS.map((s) => (
              <button
                key={s.id}
                onClick={() => url.set({ section: s.id === 'profile' ? null : s.id })}
                className={cn(
                  'flex h-8 w-full items-center gap-2.5 rounded-md px-2.5 text-sm font-medium transition-colors duration-120',
                  section === s.id ? 'bg-surface-selected text-fg' : 'text-fg-muted hover:bg-surface-hover hover:text-fg',
                )}
              >
                <s.icon className={cn('size-4', section === s.id ? 'text-primary' : 'text-fg-subtle')} strokeWidth={1.75} />
                {s.label}
              </button>
            ))}
          </nav>
          <div className="min-w-0 flex-1">
            {error ? (
              <ErrorState error={error} onRetry={() => (settings.error ? settings.refetch() : profile.refetch())} />
            ) : !settings.data || !profile.data ? (
              <div className="space-y-3">
                <Skeleton className="h-16" />
                <Skeleton className="h-64" />
              </div>
            ) : section === 'sources' ? (
              <SourcesSection settings={settings.data} />
            ) : section === 'schedule' ? (
              <ScheduleSection key={JSON.stringify(settings.data.values.schedule)} settings={settings.data} />
            ) : section === 'models' ? (
              <ModelsSection key={JSON.stringify(settings.data.values.models)} settings={settings.data} />
            ) : section === 'email' ? (
              <EmailSection key={JSON.stringify(settings.data.values.smtp)} settings={settings.data} />
            ) : section === 'data' ? (
              <DataSection settings={settings.data} />
            ) : (
              <ProfileSection key={JSON.stringify(profile.data)} profile={profile.data} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
