import { Navigate } from 'react-router'
import { PageHeader } from '@/components/app/PageHeader'
import { TourButton } from '@/components/app/tour/TourButton'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useMotivation } from '@/lib/queries/motivation'
import { BreatheTab } from './BreatheTab'
import { GoalsTab } from './GoalsTab'
import { ShopTab } from './ShopTab'
import { StartTab } from './StartTab'
import { WinsTab } from './WinsTab'
import { WoopTab } from './WoopTab'

const TABS = [
  { id: 'breathe', label: 'Breathe' },
  { id: 'start', label: 'Start' },
  { id: 'plan', label: 'Plan' },
  { id: 'wins', label: 'Wins' },
  { id: 'goals', label: 'My goals' },
  { id: 'shop', label: 'Shop' },
] as const
type Tab = (typeof TABS)[number]['id']

/** Motiv Center: small tools for the hard days. Nothing here is required by the job flow. */
export default function MotivCenterPage() {
  const url = useSearchParamState()
  const summary = useMotivation()
  const raw = url.get('tab')
  const tab: Tab = TABS.some((t) => t.id === raw) ? (raw as Tab) : 'breathe'

  if (summary.isPending) return <Skeleton className="m-6 h-64" />
  if (summary.data && !summary.data.enabled) return <Navigate to="/" replace />

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Motiv Center"
        description="Breathe, start small, plan for the hard parts, see your wins, and remember what you're working for."
        actions={<TourButton tour="motivation" label="How it works" />}
        className="pb-0"
      >
        <Tabs data-tour="motiv-tabs" value={tab} onValueChange={(v) => url.set({ tab: v === 'breathe' ? null : v })}>
          <TabsList>
            {TABS.map((t) => (
              <TabsTrigger key={t.id} value={t.id}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-6">
        {tab === 'breathe' ? <BreatheTab /> : tab === 'start' ? <StartTab /> : tab === 'plan' ? <WoopTab /> : tab === 'wins' ? <WinsTab /> : tab === 'goals' ? <GoalsTab /> : <ShopTab />}
      </div>
    </div>
  )
}
