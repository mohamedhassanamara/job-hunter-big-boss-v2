import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

const CHIPS = ['Shorter', "More focused on this job's core skill", 'Less jargon']

/** "New summary": asks what should change (optional) before the CV model edits the summary toward
 * it. Empty = a plain new summary. */
export function SummaryFeedbackButton({ busy, disabled, onSubmit }: { busy: boolean; disabled: boolean; onSubmit: (feedback: string) => void }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [chips, setChips] = useState<string[]>([])

  const submit = () => {
    const feedback = [...chips, text.trim()].filter(Boolean).join('. ')
    setOpen(false)
    setText('')
    setChips([])
    onSubmit(feedback)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" disabled={disabled || busy} data-tour="cv-new-summary">
          <RefreshCw className={busy ? 'animate-spin' : undefined} />
          {busy ? 'Writing…' : 'New summary'}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 space-y-3">
        <div className="space-y-1.5">
          <Label htmlFor="summary-feedback">What should change?</Label>
          <p className="text-2xs text-fg-subtle">Optional. The current summary, your note, the job and your experience go to the CV model, which edits the summary toward your note. Bullets and layout stay as they are.</p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {CHIPS.map((chip) => {
            const on = chips.includes(chip)
            return (
              <button
                key={chip}
                type="button"
                aria-pressed={on}
                onClick={() => setChips((c) => (on ? c.filter((x) => x !== chip) : [...c, chip]))}
                className={cn('h-6 rounded-full border px-2.5 text-xs transition-colors duration-120', on ? 'border-primary bg-primary-subtle text-fg' : 'border-border text-fg-muted hover:bg-surface-hover hover:text-fg')}
              >
                {chip}
              </button>
            )
          })}
        </div>
        <Textarea id="summary-feedback" rows={3} value={text} placeholder="e.g. mention the lakehouse first" onChange={(e) => setText(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button variant="default" size="sm" onClick={submit}>
            {text.trim() || chips.length ? 'Write with feedback' : 'Write new summary'}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
