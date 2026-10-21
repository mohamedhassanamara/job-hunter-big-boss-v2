import { RefreshCw } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/input'

/** "Regenerate" asks what should change (optional): the model edits the current version toward
 * it instead of starting over, with the same sources and rules. Shared by emails, LinkedIn
 * messages and letters. `extra` holds options that belong with it (a language, for emails). */
export function RegenerateDialog({
  open,
  onClose,
  title,
  hint,
  pending,
  extra,
  onSubmit,
}: {
  open: boolean
  onClose: () => void
  title: string
  hint?: string
  pending?: boolean
  extra?: ReactNode
  onSubmit: (feedback: string) => void
}) {
  const [text, setText] = useState('')
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={title} className="max-w-lg p-0">
        <div className="space-y-3 px-5 py-4">
          <div>
            <h2 className="text-md font-semibold tracking-tight">{title}</h2>
            <p className="text-sm text-fg-muted">
              {hint ?? 'Claude edits the current version toward your feedback instead of starting over. Every fact is checked again, and the older version is kept so you can go back.'}
            </p>
          </div>
          {extra}
          <div className="space-y-1.5">
            <Label htmlFor="regen-feedback">What should change? (optional)</Label>
            <Textarea
              id="regen-feedback"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. shorter, lead with the Flutter app, drop the second proof…"
              className="min-h-28 text-sm"
              autoFocus
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="default"
            disabled={pending}
            onClick={() => {
              onSubmit(text.trim())
              setText('')
            }}
          >
            <RefreshCw className={pending ? 'animate-spin' : undefined} />
            {text.trim() ? 'Regenerate with feedback' : 'Regenerate'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
