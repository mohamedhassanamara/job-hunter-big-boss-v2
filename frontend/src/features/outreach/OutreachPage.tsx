import { PageHeader } from '@/components/app/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useNavCounts } from '@/lib/queries/workflow'
import { QueueTab } from './QueueTab'
import { ReviewTab } from './ReviewTab'

export default function OutreachPage() {
  const url = useSearchParamState()
  const tab = url.get('tab') === 'queue' ? 'queue' : 'review'
  const counts = useNavCounts()

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Outreach"
        description="Review every email before it's queued. Sends go out one at a time."
        className="pb-0"
      >
        <Tabs
          value={tab}
          onValueChange={(v) => url.set({ tab: v === 'review' ? null : v, draft: null, status: null })}
        >
          <TabsList>
            <TabsTrigger value="review" count={counts.data?.outreach_review}>
              Review
            </TabsTrigger>
            <TabsTrigger value="queue" count={counts.data?.queue_pending}>
              Send queue
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-y-auto">{tab === 'review' ? <ReviewTab /> : <QueueTab />}</div>
    </div>
  )
}
