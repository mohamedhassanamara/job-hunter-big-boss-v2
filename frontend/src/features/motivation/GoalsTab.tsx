import { ArrowLeft, ArrowRight, ImagePlus, Play, Target, Trash2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'
import { EmptyState, ErrorState } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { usePendingDelete } from '@/hooks/usePendingDelete'
import { motivationFile, useAddGoal, useDeleteGoal, useEditGoal, useGoals, useOrderGoals } from '@/lib/queries/motivation'
import { useSettings } from '@/lib/queries/library'
import type { GoalTile } from '@/lib/types'
import { cn } from '@/lib/utils'

const ACCEPT = 'image/png,image/jpeg,image/webp,image/gif,video/mp4,video/webm,video/quicktime'

function Media({ tile, large }: { tile: GoalTile; large?: boolean }) {
  const src = motivationFile(tile.file_name)
  if (tile.kind === 'video') {
    return large ? (
      <video src={src} controls autoPlay playsInline className="max-h-[70vh] w-full rounded-lg bg-bg-subtle object-contain" />
    ) : (
      <video src={`${src}#t=0.1`} muted playsInline preload="metadata" className="size-full object-cover" />
    )
  }
  return <img src={src} alt={tile.caption || tile.original_name} className={large ? 'max-h-[70vh] w-full rounded-lg object-contain' : 'size-full object-cover'} />
}

function TileDialog({ tile, onClose }: { tile: GoalTile | null; onClose: () => void }) {
  const edit = useEditGoal()
  const [caption, setCaption] = useState(tile?.caption ?? '')
  return (
    <Dialog open={tile !== null} onOpenChange={(o) => !o && onClose()}>
      {tile && (
        <DialogContent title={tile.caption || 'My goal'} className="top-[8%] max-w-5xl">
          <div className="grid gap-5 p-5 md:grid-cols-[1fr_280px]">
            <Media tile={tile} large />
            <div className="flex flex-col gap-3 pt-6">
              {tile.caption ? <p className="text-base leading-relaxed whitespace-pre-wrap">{tile.caption}</p> : <p className="text-sm text-fg-muted">Add a few words: why this matters to you.</p>}
              <Textarea value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Your text" aria-label="Caption" className="min-h-24" />
              <Button
                size="sm"
                variant="secondary"
                className="self-start"
                disabled={caption.trim() === tile.caption || edit.isPending}
                onClick={() => edit.mutate({ id: tile.id, caption }, { onSuccess: () => toast.success('Text saved'), onError: (e) => toast.error(e.message) })}
              >
                Save text
              </Button>
            </div>
          </div>
        </DialogContent>
      )}
    </Dialog>
  )
}

/** My goals: your own images and videos, each with a few words, to look at when you need it. */
export function GoalsTab() {
  const goals = useGoals()
  const add = useAddGoal()
  const order = useOrderGoals()
  const del = useDeleteGoal()
  const pending = usePendingDelete((id) => del.mutate(id))
  const settings = useSettings()
  const limit = (settings.data?.values.motivation as { max_upload_mb?: number } | undefined)?.max_upload_mb ?? 100
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [openId, setOpenId] = useState<number | null>(null)
  const tiles = (goals.data ?? []).filter((t) => !pending.hidden.has(t.id))
  const open = tiles.find((t) => t.id === openId) ?? null

  const upload = (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      if (file.size > limit * 1024 * 1024) {
        toast.error(`${file.name} is larger than ${limit} MB (Settings → Motivation)`)
        continue
      }
      add.mutate({ file }, { onSuccess: () => toast.success(`${file.name} added`), onError: (e) => toast.error(`${file.name}: ${e.message}`) })
    }
  }
  const move = (index: number, by: number) => {
    const ids = tiles.map((t) => t.id)
    const to = index + by
    if (to < 0 || to >= ids.length) return
    ;[ids[index], ids[to]] = [ids[to], ids[index]]
    order.mutate([...ids, ...(goals.data ?? []).filter((t) => pending.hidden.has(t.id)).map((t) => t.id)])
  }

  const picker = (
    <input ref={input} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => (e.target.files && upload(e.target.files), (e.target.value = ''))} />
  )

  if (goals.error) return <ErrorState error={goals.error} onRetry={() => goals.refetch()} />
  return (
    <div
      className="mx-auto max-w-6xl space-y-4 py-6"
      data-tour="motiv-goals"
      onDragOver={(e) => (e.preventDefault(), setDragging(true))}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        upload(e.dataTransfer.files)
      }}
    >
      {picker}
      <div className="flex items-center gap-3">
        <div className="flex-1 space-y-1">
          <h2 className="text-base font-semibold">My goals</h2>
          <p className="text-sm text-fg-muted">Images and videos of what you're working toward. Stored only on this computer (up to {limit} MB each).</p>
        </div>
        <Button variant="default" onClick={() => input.current?.click()} disabled={add.isPending}>
          <Upload />
          {add.isPending ? 'Uploading…' : 'Add images or videos'}
        </Button>
      </div>
      {goals.isPending ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="aspect-[4/3]" />
          ))}
        </div>
      ) : tiles.length === 0 ? (
        <div className={cn('rounded-lg border-2 border-dashed', dragging ? 'border-primary bg-primary-subtle' : 'border-border-strong')}>
          <EmptyState
            icon={Target}
            title="Picture where you're going"
            description="Drop images or videos here: the city, the team, the life you're working for. Click one later to see it large with your own words."
            action={
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => input.current?.click()}>
                  <ImagePlus />
                  Choose files
                </Button>
                <TourButton tour="motivation" />
              </div>
            }
          />
        </div>
      ) : (
        <div className={cn('grid grid-cols-2 gap-3 rounded-lg md:grid-cols-3 xl:grid-cols-4', dragging && 'ring-2 ring-primary ring-offset-4 ring-offset-bg')}>
          {tiles.map((t, i) => (
            <figure key={t.id} className="group overflow-hidden rounded-lg border border-border bg-surface">
              <button className="relative block aspect-[4/3] w-full overflow-hidden bg-bg-subtle" onClick={() => setOpenId(t.id)} aria-label={`Open ${t.caption || t.original_name}`}>
                <Media tile={t} />
                {t.kind === 'video' && (
                  <span className="absolute inset-0 flex items-center justify-center">
                    <span className="flex size-10 items-center justify-center rounded-full bg-overlay text-primary-fg">
                      <Play className="size-4" />
                    </span>
                  </span>
                )}
              </button>
              <figcaption className="flex items-center gap-1 px-3 py-2">
                <span className="min-w-0 flex-1 truncate text-sm">{t.caption || <span className="text-fg-subtle">No text yet</span>}</span>
                <span className="flex opacity-0 transition-opacity duration-120 group-focus-within:opacity-100 group-hover:opacity-100">
                  <Button size="icon-sm" variant="ghost" aria-label="Move earlier" disabled={i === 0} onClick={() => move(i, -1)}>
                    <ArrowLeft />
                  </Button>
                  <Button size="icon-sm" variant="ghost" aria-label="Move later" disabled={i === tiles.length - 1} onClick={() => move(i, 1)}>
                    <ArrowRight />
                  </Button>
                  <Button size="icon-sm" variant="ghost" aria-label="Delete" onClick={() => pending.remove(t.id, t.kind === 'video' ? 'Video' : 'Image')}>
                    <Trash2 />
                  </Button>
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
      <TileDialog key={open?.id ?? 'none'} tile={open} onClose={() => setOpenId(null)} />
    </div>
  )
}
