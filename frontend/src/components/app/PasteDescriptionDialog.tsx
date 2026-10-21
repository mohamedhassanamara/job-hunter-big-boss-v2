import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/input'
import { usePasteDescription } from '@/lib/queries/workflow'

/** Paste the full job description (for short snippets and sites that block fetching); the job is rescored. */
export function PasteDescriptionDialog({ jobId, open, onClose }: { jobId: number; open: boolean; onClose: () => void }) {
  const paste = usePasteDescription()
  const [text, setText] = useState('')
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Paste the full description" className="max-w-2xl p-0">
        <div className="space-y-3 px-5 py-4">
          <div>
            <h2 className="text-md font-semibold tracking-tight">Paste the full description</h2>
            <p className="text-sm text-fg-muted">
              Open the listing, copy the whole job description and paste it here. The job is rescored
              on the full text (confidence: high).
            </p>
          </div>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste the job description…"
            className="min-h-64 text-sm"
            autoFocus
          />
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <span className="mr-auto text-xs text-fg-subtle tabular-nums">{text.length} characters</span>
          <Button size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="default"
            disabled={text.trim().length < 200 || paste.isPending}
            onClick={() =>
              paste.mutate(
                { jobId, description: text },
                {
                  onSuccess: () => {
                    toast.success('Description saved; rescoring on the full text')
                    setText('')
                    onClose()
                  },
                  onError: (e) => toast.error(e.message),
                },
              )
            }
          >
            Save & rescore
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
