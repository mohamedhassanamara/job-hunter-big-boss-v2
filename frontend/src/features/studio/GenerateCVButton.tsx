import { ChevronDown, Download, FileText, Loader2, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { api, apiUrl } from '@/lib/api'
import { useCvTracks, useGenerateTrackCv, useTrackCvStatus, type TrackOption } from '@/lib/queries/trackCv'

/** Studio → Generate CV: a general CV for a track or the all-purpose master. It is never saved:
 * preview it, download it (the server then deletes it) or close it. */
export function GenerateCVButton() {
  const tracks = useCvTracks()
  const generate = useGenerateTrackCv()
  const [id, setId] = useState<string | null>(null)
  const [picked, setPicked] = useState<TrackOption | null>(null)
  const status = useTrackCvStatus(id)
  const cv = status.data
  const running = generate.isPending || cv?.status === 'running'
  const open = id !== null

  const close = () => {
    if (id) void api.del(`/cv/generate/${id}`).catch(() => undefined)
    setId(null)
    setPicked(null)
    generate.reset()
  }

  const start = (option: TrackOption) => {
    setPicked(option)
    generate.mutate(
      { track: option.value },
      {
        onSuccess: (r) => setId(r.id),
        onError: (e) => {
          setPicked(null)
          toast.error('Could not start the CV', { description: e instanceof Error ? e.message : undefined })
        },
      },
    )
  }

  const options = tracks.data ?? [{ value: 'all_purpose', label: 'All-Purpose (Master / General)' }]
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="default" disabled={running} data-tour="studio-generate">
            {running ? <Loader2 className="animate-spin" /> : <Sparkles />}
            Generate CV
            <ChevronDown />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72">
          <DropdownMenuLabel className="px-2 py-1 text-xs text-fg-subtle">General CV, not tied to a job</DropdownMenuLabel>
          <DropdownMenuItem onSelect={() => start(options[0])}>
            <FileText />
            {options[0].label}
          </DropdownMenuItem>
          {options.length > 1 && <DropdownMenuSeparator />}
          {options.slice(1).map((o) => (
            <DropdownMenuItem key={o.value} onSelect={() => start(o)}>
              <FileText />
              {o.label}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={open || (generate.isPending && !!picked)} onOpenChange={(o) => !o && close()}>
        <DialogContent
          title="Generated CV"
          description="A general CV that is not saved. Download it, or it is deleted when you close this."
          className="top-[6%] flex h-[88vh] max-w-3xl flex-col"
        >
          <div className="border-b border-border px-5 py-3 pr-12">
            <p className="text-sm font-medium">{picked?.label ?? 'Generated CV'}</p>
            <p className="text-xs text-fg-muted">Not saved: it disappears after download, when you close this, or when the server stops.</p>
          </div>
          <div className="min-h-0 flex-1">
            {!cv || cv.status === 'running' ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-fg-muted" role="status">
                <Loader2 className="size-5 animate-spin" />
                Tailoring your CV… usually under a minute.
              </div>
            ) : cv.status === 'failed' ? (
              <div className="p-5 text-sm text-danger-fg" role="alert">
                {cv.error ?? 'Generation failed.'}
              </div>
            ) : (
              <iframe title="Generated CV" src={apiUrl(`/cv/generate/${cv.id}/pdf`)} className="size-full" />
            )}
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
            {cv?.status === 'ready' && (
              <span className="mr-auto text-xs text-fg-muted">
                {cv.page_count} page · {cv.model}
                {cv.issues.length > 0 ? ` · ${cv.issues.length} note${cv.issues.length > 1 ? 's' : ''}` : ''}
              </span>
            )}
            <Button variant="outline" onClick={close}>
              Close
            </Button>
            {cv?.status === 'ready' && (
              <Button variant="default" asChild>
                <a href={apiUrl(`/cv/generate/${cv.id}/pdf`, { download: true })} onClick={() => setTimeout(close, 800)}>
                  <Download />
                  Download PDF
                </a>
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
