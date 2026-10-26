import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useRegenEstimate } from '@/lib/queries/workflow'
import type { CVRegenMode } from '@/lib/types'
import { cn } from '@/lib/utils'

const MODES: { value: CVRegenMode; label: string; hint: string }[] = [
  { value: 'whole', label: 'Whole CV', hint: 'A new draft: bullets, layout and summary. With feedback the new summary is then written toward it.' },
  { value: 'summary', label: 'Summary only', hint: 'Bullets and layout stay; only the summary is rewritten (toward your feedback, if any).' },
]

/** One box for every selected CV: optional feedback, whole CV or summary only, the request estimate
 * against the Gemini daily cap, and a confirmation above 20. Nothing is approved: each result is a new draft. */
export function RegenerateSelectedDialog({
  open,
  onClose,
  count,
  approvedCount,
  pending,
  onSubmit,
}: {
  open: boolean
  onClose: () => void
  count: number
  approvedCount: number
  pending: boolean
  onSubmit: (mode: CVRegenMode, feedback: string, confirm: boolean) => void
}) {
  const [mode, setMode] = useState<CVRegenMode>('whole')
  const [feedback, setFeedback] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const estimate = useRegenEstimate(count, mode, feedback, open)
  const est = estimate.data
  const needsConfirm = Boolean(est?.needs_confirmation)

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Regenerate selected CVs" className="max-w-lg p-0">
        <div className="space-y-3 px-5 py-4">
          <div>
            <h2 className="text-md font-semibold tracking-tight">
              Regenerate {count} CV{count === 1 ? '' : 's'}
            </h2>
            <p className="text-sm text-fg-muted">They are written in the background with the CV model from Settings → Models. Each result is a new draft; nothing is approved for you.</p>
          </div>
          <div role="radiogroup" aria-label="What to regenerate" className="grid grid-cols-2 gap-2">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={mode === m.value}
                onClick={() => setMode(m.value)}
                className={cn(
                  'rounded-lg border px-3 py-2 text-left transition-colors duration-120',
                  mode === m.value ? 'border-primary bg-surface-selected' : 'border-border hover:bg-surface-hover',
                )}
              >
                <p className="text-sm font-medium">{m.label}</p>
                <p className="text-2xs text-fg-muted">{m.hint}</p>
              </button>
            ))}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="regen-batch-feedback">What should change? (optional, applies to every selected CV)</Label>
            <Textarea
              id="regen-batch-feedback"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder={mode === 'whole' ? 'Empty: every CV is regenerated from scratch.' : 'e.g. shorter, lead with the backend work…'}
              className="min-h-20 text-sm"
              autoFocus
            />
          </div>
          {approvedCount > 0 && (
            <p className="rounded-md border border-border bg-surface px-3 py-2 text-xs text-fg-muted">
              {approvedCount} of these {approvedCount === 1 ? 'has' : 'have'} an approved CV. It stays approved until you approve the new draft.
            </p>
          )}
          {est && (
            <p className="text-xs text-fg-muted" data-testid="regen-estimate">
              About {est.requests} request{est.requests === 1 ? '' : 's'} ({est.per_cv} per CV) on {est.provider === 'gemini' ? 'Gemini' : est.provider === 'apinex' ? 'APInex' : 'Claude'}
              {est.remaining_gemini != null && <> · Gemini has {est.remaining_gemini} of {est.gemini_cap} requests left today</>}.
              {est.exceeds_remaining && <span className="text-warning-fg"> That is more than what is left today: the rest waits for the reset.</span>}
            </p>
          )}
          {needsConfirm && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
              Yes, regenerate more than {est?.confirm_above} CVs
            </label>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <Button size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" variant="default" disabled={pending || count === 0 || (needsConfirm && !confirmed)} onClick={() => onSubmit(mode, feedback.trim(), confirmed)}>
            <RefreshCw className={pending ? 'animate-spin' : undefined} />
            Regenerate {count}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
