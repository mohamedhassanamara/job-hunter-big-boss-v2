import { Check, CircleX, Copy, LoaderCircle, ShieldAlert, Sparkles, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { ClaimCheck } from '@/components/app/verify/ClaimCheck'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/input'
import { useExternalCheck, useExternalPrompt, useExternalSave } from '@/lib/queries/workflow'
import type { EmailMode, ExternalCheck, ExternalPrompt, VerificationState } from '@/lib/types'
import { cn } from '@/lib/utils'

const MODES: { value: EmailMode; label: string }[] = [
  { value: 'applied', label: 'Application follow-up' },
  { value: 'speculative', label: 'Speculative email' },
]

/** Write the email with another AI: copy one self-contained prompt, then bring the result back
 * through the checks and the claim verifier before saving it as a draft. */
export function ExternalAIDialog({ appId, open, onClose, defaultMode }: { appId: number; open: boolean; onClose: () => void; defaultMode: EmailMode }) {
  const [mode, setMode] = useState<EmailMode>(defaultMode)
  const [prompt, setPrompt] = useState<ExternalPrompt | null>(null)
  const [pasted, setPasted] = useState('')
  const [checked, setChecked] = useState<ExternalCheck | null>(null)
  const build = useExternalPrompt(appId)
  const check = useExternalCheck(appId)
  const save = useExternalSave(appId)

  useEffect(() => {
    if (!open) return
    build.mutate({ mode }, { onSuccess: setPrompt, onError: (e) => toast.error(e.message) })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- rebuilt when opened or when the mode changes
  }, [open, mode])

  const copy = async () => {
    if (!prompt) return
    try {
      await navigator.clipboard.writeText(prompt.prompt)
      toast.success('Prompt copied', { description: `${prompt.chars.toLocaleString()} characters · ${prompt.items.length} experience item${prompt.items.length === 1 ? '' : 's'}` })
    } catch {
      toast.error('Couldn’t copy: select the prompt below and copy it by hand')
    }
  }

  const state: VerificationState = checked?.verification.status ?? 'none'
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Copy for another AI" className="max-w-3xl p-0">
        <div className="max-h-[80vh] space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <h2 className="text-md font-semibold tracking-tight">Write the email with another AI</h2>
            <p className="text-sm text-fg-muted">Copy the prompt into Gemini, ChatGPT or similar, then paste its email back here: it goes through the same checks and the claim verifier before you can save it.</p>
          </div>

          <div className="space-y-2">
            <div role="radiogroup" aria-label="Email type" className="flex gap-1.5">
              {MODES.map((m) => (
                <Button key={m.value} size="sm" variant={mode === m.value ? 'outline' : 'ghost'} role="radio" aria-checked={mode === m.value} onClick={() => setMode(m.value)}>
                  {m.label}
                </Button>
              ))}
            </div>
            <p className="flex items-start gap-2 rounded-md border border-border bg-warning-bg px-3 py-2 text-sm text-warning-fg">
              <ShieldAlert className="mt-0.5 size-4 shrink-0" />
              <span>{prompt?.note ?? 'This prompt contains your experience and the full job listing. Only paste it into AI tools you trust.'}</span>
            </p>
            {prompt?.language && (
              <p className="text-xs text-fg-subtle">
                Language: {prompt.language.reason}
              </p>
            )}
            {prompt?.listing_short && <p className="text-xs text-warning-fg">The saved listing is a short snippet: the other AI can’t see requirements like residency. Paste the full description on the job first.</p>}
            <div className="flex items-center gap-2">
              <Button size="sm" variant="default" onClick={() => void copy()} disabled={!prompt || build.isPending}>
                {build.isPending ? <LoaderCircle className="animate-spin" /> : <Copy />}
                Copy prompt
              </Button>
              {prompt && <span className="text-xs text-fg-subtle tabular-nums">{prompt.chars.toLocaleString()} characters</span>}
            </div>
            {prompt && (
              <details className="rounded-md border border-border bg-surface px-3 py-2">
                <summary className="cursor-default text-xs font-medium text-fg-subtle">See the prompt</summary>
                <pre className="mt-2 max-h-64 overflow-auto text-xs whitespace-pre-wrap text-fg-muted">{prompt.prompt}</pre>
              </details>
            )}
          </div>

          <div className="space-y-1.5 border-t border-border pt-4">
            <Label htmlFor="external-draft">Paste a draft from another AI</Label>
            <Textarea
              id="external-draft"
              value={pasted}
              onChange={(e) => {
                setPasted(e.target.value)
                setChecked(null)
              }}
              placeholder={'Subject: …\n\nHi …'}
              className="min-h-40 text-sm"
            />
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                disabled={pasted.trim().length < 40 || check.isPending}
                onClick={() => check.mutate({ text: pasted, mode }, { onSuccess: setChecked, onError: (e) => toast.error(e.message) })}
              >
                {check.isPending ? <LoaderCircle className="animate-spin" /> : <Sparkles />}
                {check.isPending ? 'Checking every claim…' : 'Check this draft'}
              </Button>
              <span className="text-xs text-fg-subtle">The claim verifier takes ~20–60 s.</span>
            </div>
          </div>

          {checked && (
            <div className="space-y-3">
              {checked.violations.length > 0 && (
                <ul className="space-y-1 rounded-md border border-border bg-surface px-3 py-2">
                  {checked.violations.map((v, i) => (
                    <li key={i} className={cn('flex items-start gap-2 text-sm', v.severity === 'error' ? 'text-danger-fg' : 'text-warning-fg')}>
                      {v.severity === 'error' ? <CircleX className="mt-0.5 size-4 shrink-0" /> : <TriangleAlert className="mt-0.5 size-4 shrink-0" />}
                      <span>{v.message}</span>
                    </li>
                  ))}
                </ul>
              )}
              <ClaimCheck verification={checked.verification} state={state} gate="approval" />
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          {checked && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setChecked(null)
                setPasted('')
              }}
            >
              Discard
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onClose}>
            Close
          </Button>
          {checked && (
            <Button
              size="sm"
              variant="default"
              disabled={save.isPending}
              onClick={() =>
                save.mutate(
                  { text: pasted, mode },
                  {
                    onSuccess: () => {
                      toast.success('Saved as the draft under review', { description: 'Review it below, then approve.' })
                      setChecked(null)
                      setPasted('')
                      onClose()
                    },
                    onError: (e) => toast.error(e.message),
                  },
                )
              }
            >
              <Check />
              Save as draft
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
