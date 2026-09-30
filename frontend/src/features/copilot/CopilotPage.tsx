import { BotMessageSquare, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { CopilotChat } from '@/components/app/copilot/CopilotChat'
import { PageHeader } from '@/components/app/PageHeader'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { relativeTime } from '@/lib/format'
import { useCopilotThread, useCopilotThreads, useDeleteCopilotThread, useNewCopilotThread } from '@/lib/queries/copilot'
import { cn } from '@/lib/utils'

/** The global Copilot: conversations about your search, with your profile and experience as
 * context (job conversations live on each Job page). */
export default function CopilotPage() {
  const url = useSearchParamState()
  const threads = useCopilotThreads()
  const create = useNewCopilotThread()
  const remove = useDeleteCopilotThread()
  const list = threads.data ?? []
  const selectedId = Number(url.get('thread')) || list[0]?.id || null
  const thread = useCopilotThread(selectedId)

  const newChat = () =>
    create.mutate(undefined, {
      onSuccess: (t) => url.set({ thread: t.id }),
      onError: (e) => toast.error(e.message),
    })

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Copilot"
        description="Ask about your search. Answers use the local model with your profile and experience; it never changes anything."
        actions={
          list.length > 0 && (
            <Button variant="default" onClick={newChat} disabled={create.isPending}>
              <Plus />
              New chat
            </Button>
          )
        }
      />
      {threads.isPending ? (
        <SkeletonRows rows={4} />
      ) : threads.error ? (
        <ErrorState error={threads.error} onRetry={() => threads.refetch()} />
      ) : list.length === 0 ? (
        <EmptyState
          icon={BotMessageSquare}
          title="No conversations yet"
          description="Ask which projects fit a track, what to add to your experience, or to draft a message. Job-specific questions go in the Copilot on each Job page."
          action={
            <div className="flex gap-2">
              <Button variant="default" onClick={newChat} disabled={create.isPending}>
                <Plus />
                Start a chat
              </Button>
              <TourButton tour="copilot" />
            </div>
          }
        />
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)]">
          <nav className="min-h-0 overflow-y-auto border-r border-border" aria-label="Conversations" data-tour="copilot-threads">
            {list.map((t) => (
              <div
                key={t.id}
                className={cn(
                  'group flex cursor-default items-center gap-2 border-b border-border px-4 py-2.5',
                  t.id === selectedId ? 'bg-surface-selected' : 'hover:bg-surface-hover',
                )}
                onClick={() => url.set({ thread: t.id })}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{t.title}</p>
                  <p className="text-xs text-fg-subtle">
                    {t.message_count} message{t.message_count === 1 ? '' : 's'} · {relativeTime(t.updated_at)}
                  </p>
                </div>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Delete conversation"
                  className="opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation()
                    remove.mutate(t.id, { onSuccess: () => (url.set({ thread: null }), toast.success('Conversation deleted')) })
                  }}
                >
                  <Trash2 />
                </Button>
              </div>
            ))}
          </nav>
          <div className="min-h-0 bg-bg">
            {thread.isPending ? (
              <div className="space-y-3 p-6">
                <Skeleton className="h-16" />
                <Skeleton className="h-24" />
              </div>
            ) : thread.error ? (
              <ErrorState error={thread.error} onRetry={() => thread.refetch()} />
            ) : thread.data ? (
              <CopilotChat key={thread.data.id} thread={thread.data} placeholder="Ask about your search, your experience, a message to write…" />
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}
