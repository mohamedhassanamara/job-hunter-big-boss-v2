import {
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import { Mail, Globe, Search, UserRoundX } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { FitBadge, StageDot } from '@/components/app/badges'
import { Tooltip } from '@/components/ui/tooltip'
import { COLUMN_LABELS, shortAge, STAGE_ORDER } from '@/lib/format'
import type { PipelineCard, Stage } from '@/lib/types'
import { cn } from '@/lib/utils'

function CardBody({ card, dragging }: { card: PipelineCard; dragging?: boolean }) {
  return (
    <div
      className={cn(
        'space-y-2 rounded-lg border border-border bg-surface p-3 shadow-sm transition-colors duration-120',
        dragging ? 'rotate-1 shadow-lg' : 'hover:border-border-strong',
      )}
    >
      <div className="flex items-start gap-2">
        <p className="line-clamp-2 flex-1 text-sm leading-snug font-medium">{card.title}</p>
        <FitBadge fit={card.fit} size="sm" />
      </div>
      <p className="truncate text-xs text-fg-muted">{card.company_name}</p>
      <div className="flex items-center gap-2 text-xs text-fg-subtle">
        {card.route === 'cold_email' && (
          <Tooltip content="Cold email">
            <Mail className="size-3.5" />
          </Tooltip>
        )}
        {card.route === 'web_apply' && (
          <Tooltip content="Web apply">
            <Globe className="size-3.5" />
          </Tooltip>
        )}
        {card.contact_tier === 'lookup_queued' && (
          <Tooltip content="Apollo lookup queued">
            <Search className="size-3.5 text-warning-dot" />
          </Tooltip>
        )}
        {card.contact_tier === 'none' && card.stage !== 'new' && card.stage !== 'closed' && (
          <Tooltip content="No contact">
            <UserRoundX className="size-3.5" />
          </Tooltip>
        )}
        {card.stage === 'closed' && card.close_reason && (
          <span className="capitalize">{card.close_reason.replace('_', ' ')}</span>
        )}
        <Tooltip content="Time in this stage">
          <span className="ml-auto tabular-nums">{shortAge(card.stage_changed_at)}</span>
        </Tooltip>
      </div>
    </div>
  )
}

function DraggableCard({ card }: { card: PipelineCard }) {
  const navigate = useNavigate()
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: card.application_id,
    data: card,
  })
  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      onClick={() => navigate(`/jobs/${card.job_id}`)}
      className={cn('cursor-grab outline-none active:cursor-grabbing', isDragging && 'opacity-30')}
    >
      <CardBody card={card} />
    </div>
  )
}

function Column({
  stage,
  cards,
  activeCard,
}: {
  stage: Stage
  cards: PipelineCard[]
  activeCard: PipelineCard | null
}) {
  const { setNodeRef, isOver } = useDroppable({ id: stage })
  const allowed = activeCard ? activeCard.allowed_stages.includes(stage) : false
  const isSource = activeCard?.stage === stage
  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex w-64 shrink-0 flex-col rounded-lg border border-transparent bg-bg-subtle transition-colors duration-120',
        activeCard && !allowed && !isSource && 'opacity-50',
        activeCard && allowed && 'border-dashed border-border-strong',
        isOver && allowed && 'border-primary bg-primary-subtle',
      )}
    >
      <div className="flex h-10 shrink-0 items-center gap-2 px-3">
        <StageDot stage={stage} />
        <span className="text-sm font-medium">{COLUMN_LABELS[stage]}</span>
        <span className="text-xs text-fg-subtle tabular-nums">{cards.length}</span>
      </div>
      <div className="flex min-h-24 flex-1 flex-col gap-2 overflow-y-auto px-2 pb-2">
        {cards.map((c) => (
          <DraggableCard key={c.application_id} card={c} />
        ))}
        {cards.length === 0 && (
          <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-xs text-fg-subtle">
            {activeCard && allowed ? 'Drop here' : 'Empty'}
          </p>
        )}
      </div>
    </div>
  )
}

export function Board({
  cards,
  onMove,
}: {
  cards: PipelineCard[]
  onMove: (card: PipelineCard, to: Stage) => void
}) {
  const [active, setActive] = useState<PipelineCard | null>(null)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))

  const onDragStart = (e: DragStartEvent) => setActive(e.active.data.current as PipelineCard)
  const onDragEnd = (e: DragEndEvent) => {
    const card = e.active.data.current as PipelineCard
    setActive(null)
    const to = e.over?.id as Stage | undefined
    if (!to || to === card.stage) return
    onMove(card, to)
  }

  return (
    <DndContext
      sensors={sensors}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={() => setActive(null)}
    >
      <div className="flex h-full gap-3 overflow-x-auto px-6 py-4">
        {STAGE_ORDER.map((stage) => (
          <Column
            key={stage}
            stage={stage}
            cards={cards.filter((c) => c.stage === stage)}
            activeCard={active}
          />
        ))}
      </div>
      <DragOverlay dropAnimation={{ duration: 150, easing: 'ease-out' }}>
        {active ? (
          <div className="w-60">
            <CardBody card={active} dragging />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  )
}
