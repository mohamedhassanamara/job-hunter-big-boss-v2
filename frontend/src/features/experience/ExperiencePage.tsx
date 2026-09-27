import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Layers, Pencil, Plus, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { PageHeader } from '@/components/app/PageHeader'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TestDataBanner } from '@/components/app/TestDataBanner'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Tooltip } from '@/components/ui/tooltip'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { pluralize } from '@/lib/format'
import {
  useDeleteExperience,
  useExperience,
  useReorderExperience,
  useSaveExperience,
} from '@/lib/queries/library'
import type { ExperienceInput, ExperienceItem, ExperienceKind } from '@/lib/types'
import { cn } from '@/lib/utils'
import { ExperienceSheet } from './ExperienceSheet'
import { formatRange, KINDS } from './kinds'

function Row({
  item,
  onEdit,
  onToggle,
  dragDisabled,
  tour,
}: {
  item: ExperienceItem
  onEdit: () => void
  onToggle: (active: boolean) => void
  dragDisabled: boolean
  tour?: string
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: item.id,
    disabled: dragDisabled,
  })
  const range = formatRange(item.start_date, item.end_date)
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      data-tour={tour}
      onClick={onEdit}
      className={cn(
        'group flex cursor-default items-center gap-3 border-b border-border bg-surface px-3 py-3 transition-colors duration-120 last:border-b-0 hover:bg-surface-hover',
        isDragging && 'relative z-10 shadow-lg',
        !item.is_active && 'opacity-60',
      )}
    >
      <button
        {...attributes}
        {...listeners}
        disabled={dragDisabled}
        onClick={(e) => e.stopPropagation()}
        aria-label="Drag to reorder"
        className="cursor-grab rounded-sm p-0.5 text-fg-subtle opacity-0 group-hover:opacity-100 focus-visible:opacity-100 active:cursor-grabbing disabled:hidden"
      >
        <GripVertical className="size-4" />
      </button>
      <button className="min-w-0 flex-1 text-left">
        <div className="flex items-baseline gap-2">
          <span className="truncate text-sm font-medium">{item.title}</span>
          {item.org && <span className="truncate text-sm text-fg-muted">{item.org}</span>}
          {item.is_placeholder && (
            <ToneBadge tone="amber" dot={false}>
              Test
            </ToneBadge>
          )}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {range && <span className="mr-1 text-xs text-fg-subtle tabular-nums">{range}</span>}
          {item.tags.slice(0, 7).map((t) => (
            <span key={t} className="rounded-sm bg-surface-hover px-1.5 text-2xs leading-5 text-fg-muted">
              {t}
            </span>
          ))}
          {item.tags.length > 7 && <span className="text-2xs text-fg-subtle">+{item.tags.length - 7}</span>}
        </div>
      </button>
      {item.bullets.length > 0 && (
        <span className="text-xs text-fg-subtle tabular-nums">{pluralize(item.bullets.length, 'bullet')}</span>
      )}
      <Tooltip content={item.is_active ? 'Used in CVs' : 'Excluded from CVs'}>
        <span onClick={(e) => e.stopPropagation()}>
          <Switch checked={item.is_active} onCheckedChange={onToggle} aria-label="Use in CVs" />
        </span>
      </Tooltip>
      <Tooltip content="Edit">
        <Button size="icon-sm" variant="ghost" onClick={onEdit} aria-label="Edit">
          <Pencil />
        </Button>
      </Tooltip>
    </div>
  )
}

export default function ExperiencePage() {
  const url = useSearchParamState()
  const { data, isPending, error, refetch } = useExperience()
  const save = useSaveExperience()
  const del = useDeleteExperience()
  const reorder = useReorderExperience()
  const [editing, setEditing] = useState<ExperienceItem | null>(null)
  const [creatingKind, setCreatingKind] = useState<ExperienceKind | null>(
    url.get('new') ? 'job' : null,
  )
  const [tagFilter, setTagFilter] = useState<string[]>([])
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  const items = useMemo(() => data ?? [], [data])
  const tagCounts = useMemo(() => {
    const counts = new Map<string, number>()
    items.forEach((i) => i.tags.forEach((t) => counts.set(t, (counts.get(t) ?? 0) + 1)))
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 18)
  }, [items])
  const visible = (i: ExperienceItem) => !tagFilter.length || tagFilter.every((t) => i.tags.includes(t))

  const closeSheet = () => {
    setEditing(null)
    setCreatingKind(null)
    if (url.get('new')) url.set({ new: null })
  }

  const onSave = (form: ExperienceInput) =>
    save.mutate(
      { id: editing?.id, data: form },
      {
        onSuccess: (saved) => {
          toast.success(editing ? 'Saved' : 'Added', { description: saved.title })
          closeSheet()
        },
        onError: (e) => toast.error(e.message),
      },
    )

  const onDelete = (item: ExperienceItem) => {
    closeSheet()
    del.mutate(item.id, {
      onSuccess: () =>
        toast('Deleted', {
          description: item.title,
          duration: 8000,
          action: {
            label: 'Undo',
            onClick: () => {
              const { id: _id, position: _p, updated_at: _u, ...rest } = item
              save.mutate({ data: rest }, { onSuccess: () => toast.success('Restored') })
            },
          },
        }),
      onError: (e) => toast.error(e.message),
    })
  }

  const onDragEnd = (kind: ExperienceKind) => (e: DragEndEvent) => {
    const { active, over } = e
    if (!over || active.id === over.id) return
    const ids = items.filter((i) => i.kind === kind).map((i) => i.id)
    const from = ids.indexOf(Number(active.id))
    const to = ids.indexOf(Number(over.id))
    const next = [...ids]
    next.splice(to, 0, next.splice(from, 1)[0])
    reorder.mutate({ kind, ids: next }, { onError: (err) => toast.error(err.message) })
  }

  const sheetOpen = editing !== null || creatingKind !== null

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Experience"
        description="Your master experience: the single source for every tailored CV and fit score."
        actions={
          items.length > 0 && (
            <Button variant="default" onClick={() => setCreatingKind('job')} data-tour="experience-add">
              <Plus />
              Add item
            </Button>
          )
        }
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl space-y-6 px-6 py-5">
          {isPending ? (
            <div className="space-y-4">
              <Skeleton className="h-8 w-2/3" />
              <Skeleton className="h-48" />
              <Skeleton className="h-32" />
            </div>
          ) : error ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : items.length === 0 ? (
            <EmptyState
              icon={Layers}
              title="Add your experience"
              description="Every tailored CV is built from these items, and fit scores compare jobs against them."
              action={
                <div className="flex gap-2">
                  <Button variant="default" size="sm" onClick={() => setCreatingKind('job')}>
                    <Plus />
                    Add first item
                  </Button>
                  <TourButton tour="experience" />
                </div>
              }
            />
          ) : (
            <>
              <TestDataBanner />
              {tagCounts.length > 0 && (
                <div data-tour="experience-tags" className="flex flex-wrap items-center gap-1.5">
                  <span className="mr-1 text-xs text-fg-subtle">Filter by tag</span>
                  {tagCounts.map(([tag, count]) => {
                    const on = tagFilter.includes(tag)
                    return (
                      <button
                        key={tag}
                        onClick={() => setTagFilter((f) => (on ? f.filter((t) => t !== tag) : [...f, tag]))}
                        className={cn(
                          'inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-xs transition-colors duration-120',
                          on
                            ? 'border-primary bg-primary-subtle text-fg'
                            : 'border-border bg-surface text-fg-muted hover:border-border-strong',
                        )}
                      >
                        {tag}
                        <span className="text-fg-subtle tabular-nums">{count}</span>
                      </button>
                    )
                  })}
                  {tagFilter.length > 0 && (
                    <Button size="xs" variant="ghost" onClick={() => setTagFilter([])}>
                      <X />
                      Clear
                    </Button>
                  )}
                </div>
              )}

              <div data-tour="experience-groups" className="space-y-6">
              {KINDS.map(({ kind, label, singular, icon: Icon }) => {
                const group = items.filter((i) => i.kind === kind)
                const shown = group.filter(visible)
                if (tagFilter.length && !shown.length) return null
                return (
                  <section key={kind}>
                    <div className="mb-2 flex items-center gap-2">
                      <Icon className="size-4 text-fg-subtle" strokeWidth={1.75} />
                      <h2 className="text-sm font-semibold">{label}</h2>
                      <span className="text-xs text-fg-subtle tabular-nums">{group.length}</span>
                      <Button size="xs" variant="ghost" className="ml-auto" onClick={() => setCreatingKind(kind)}>
                        <Plus />
                        Add {singular.toLowerCase()}
                      </Button>
                    </div>
                    {shown.length === 0 ? (
                      <button
                        onClick={() => setCreatingKind(kind)}
                        className="w-full rounded-lg border border-dashed border-border-strong px-4 py-5 text-sm text-fg-muted hover:bg-surface-hover"
                      >
                        No {label.toLowerCase()} yet. Add one.
                      </button>
                    ) : (
                      <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
                        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd(kind)}>
                          <SortableContext items={shown.map((i) => i.id)} strategy={verticalListSortingStrategy}>
                            {shown.map((item, i) => (
                              <Row
                                key={item.id}
                                tour={kind === 'job' && i === 0 ? 'experience-row' : undefined}
                                item={item}
                                dragDisabled={tagFilter.length > 0}
                                onEdit={() => setEditing(item)}
                                onToggle={(is_active) =>
                                  save.mutate(
                                    { id: item.id, data: { is_active } },
                                    {
                                      onSuccess: () =>
                                        toast.success(is_active ? 'Included in CVs' : 'Excluded from CVs', {
                                          description: item.title,
                                        }),
                                    },
                                  )
                                }
                              />
                            ))}
                          </SortableContext>
                        </DndContext>
                      </div>
                    )}
                  </section>
                )
              })}
              </div>
            </>
          )}
        </div>
      </div>
      {sheetOpen && (
        <ExperienceSheet
          key={editing?.id ?? `new-${creatingKind}`}
          open
          item={editing}
          defaultKind={creatingKind ?? 'job'}
          saving={save.isPending}
          onClose={closeSheet}
          onSave={onSave}
          onDelete={onDelete}
        />
      )}
    </div>
  )
}
