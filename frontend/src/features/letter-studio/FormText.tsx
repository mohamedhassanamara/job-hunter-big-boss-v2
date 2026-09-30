import { Copy } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { CoverLetter } from '@/lib/types'
import { cn } from '@/lib/utils'

/** The form's question and its text box's character limit (what the form text answers). */
export function FormQuestion({
  question,
  limit,
  onChange,
}: {
  question: string
  limit: string
  onChange: (next: { question?: string; limit?: string }) => void
}) {
  return (
    <div data-tour="letter-form-question" className="grid grid-cols-[minmax(0,1fr)_7rem] gap-3">
      <div className="space-y-1.5">
        <Label htmlFor="form-question">The form's question</Label>
        <Textarea
          id="form-question"
          value={question}
          placeholder="Expliquez-nous pourquoi vous souhaitez nous rejoindre"
          className="min-h-10 [field-sizing:content]"
          onChange={(e) => onChange({ question: e.target.value })}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="form-limit">Max characters</Label>
        <Input id="form-limit" type="number" min={100} value={limit} placeholder="optional" onChange={(e) => onChange({ limit: e.target.value })} />
      </div>
    </div>
  )
}

/** Exactly what goes into the text box, with its character count and a Copy button. */
export function FormPreview({ letter }: { letter: CoverLetter }) {
  const over = letter.char_limit != null && letter.length > letter.char_limit
  const copy = () =>
    navigator.clipboard.writeText(letter.text).then(
      () => toast.success('Form text copied', { description: 'Paste it into the text box.' }),
      () => toast.error("Couldn't copy to the clipboard"),
    )
  return (
    <div className="flex h-full flex-col p-6">
      <div className="mb-3 flex items-center gap-3">
        <p className="flex-1 truncate text-sm text-fg-muted">{letter.question}</p>
        <span className={cn('text-xs tabular-nums', over ? 'font-medium text-danger-fg' : 'text-fg-subtle')}>
          {letter.char_limit != null ? `${letter.length}/${letter.char_limit} characters` : `${letter.length} characters`}
        </span>
        <Button size="sm" onClick={copy}>
          <Copy />
          Copy
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-border bg-surface p-5 text-sm leading-relaxed whitespace-pre-wrap shadow-sm">
        {letter.text}
      </div>
    </div>
  )
}
