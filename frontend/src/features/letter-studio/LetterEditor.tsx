import { CircleCheck, CircleX, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { Input, Textarea } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tooltip } from '@/components/ui/tooltip'
import { usePatchLetter } from '@/lib/queries/letters'
import type { CoverLetter, LetterPatchInput, Violation } from '@/lib/types'
import { cn } from '@/lib/utils'

function Checks({ violations }: { violations: Violation[] }) {
  if (violations.length === 0)
    return (
      <p data-tour="letter-checks" className="flex items-center gap-2 rounded-md bg-success-bg px-3 py-2 text-sm text-success-fg">
        <CircleCheck className="size-4" />
        Every check passed: grounded in your CV and the listing, one ask, the right length, no banned phrases, one page.
      </p>
    )
  return (
    <ul data-tour="letter-checks" className="space-y-1 rounded-md border border-border bg-surface px-3 py-2">
      {violations.map((v, i) => (
        <li key={i} className={cn('flex items-start gap-2 text-sm', v.severity === 'error' ? 'text-danger-fg' : 'text-warning-fg')}>
          {v.severity === 'error' ? <CircleX className="mt-0.5 size-4 shrink-0" /> : <TriangleAlert className="mt-0.5 size-4 shrink-0" />}
          <span>
            {v.where && v.where !== 'letter' && <span className="font-medium">{v.where}: </span>}
            {v.message}
          </span>
        </li>
      ))}
    </ul>
  )
}

/** What each generated sentence is based on (hover a badge for the cited item). */
function Sources({ letter }: { letter: CoverLetter }) {
  const generated = letter.paragraphs.filter((p) => !p.edited)
  if (generated.length === 0) return null
  return (
    <details className="rounded-md border border-border bg-surface px-3 py-2 text-sm">
      <summary className="cursor-default text-xs font-medium text-fg-subtle">Where each sentence comes from</summary>
      <ul className="mt-2 space-y-1.5">
        {generated.flatMap((p, pi) =>
          p.sentences.map((s, i) => (
            <li key={`${pi}-${i}`} className="flex items-start gap-2">
              <span className="flex-1">{s.text}</span>
              {s.about_job ? (
                <ToneBadge tone="gray" dot={false}>
                  the listing
                </ToneBadge>
              ) : (
                s.citations.map((c) => (
                  <Tooltip key={c} content={letter.sources[String(c)] ?? `item ${c}`}>
                    <span>
                      <ToneBadge tone="blue" dot={false}>
                        {(letter.sources[String(c)] ?? `#${c}`).split(' · ')[0]}
                      </ToneBadge>
                    </span>
                  </Tooltip>
                ))
              )}
            </li>
          )),
        )}
      </ul>
    </details>
  )
}

/** Salutation, paragraphs and the closing ask, autosaved (700ms) and re-checked; the PDF re-renders. */
export function LetterEditor({ letter, onNewVersion }: { letter: CoverLetter; onNewVersion: (id: number) => void }) {
  const patch = usePatchLetter()
  const [salutation, setSalutation] = useState(letter.salutation)
  const [paragraphs, setParagraphs] = useState(letter.paragraphs.map((p) => p.text))
  const [ask, setAsk] = useState(letter.ask)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const timer = useRef<number | undefined>(undefined)
  const pending = useRef<LetterPatchInput>({})
  const readOnly = letter.status === 'superseded'

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const queueSave = (next: LetterPatchInput) => {
    pending.current = { ...pending.current, ...next }
    setSaveState('saving')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      const body = pending.current
      pending.current = {}
      patch.mutate(
        { id: letter.id, ...body },
        {
          onSuccess: (saved) => {
            setSaveState('saved')
            if (saved.id !== letter.id) {
              toast.success(`Changes saved as a new draft (v${saved.version})`, { description: 'The version you sent stays locked.' })
              onNewVersion(saved.id)
            }
          },
          onError: (e) => {
            setSaveState('idle')
            toast.error(`Couldn't save: ${e.message}`)
          },
        },
      )
    }, 700)
  }

  const note = readOnly
    ? 'Superseded, read only'
    : saveState === 'saving'
      ? 'Saving…'
      : saveState === 'saved'
        ? 'All changes saved'
        : letter.locked_at
          ? 'Sent with your application: changes create a new draft'
          : letter.status === 'approved'
            ? 'Editing sends it back to review'
            : 'Edit freely: checks and the PDF update'

  return (
    <div className="space-y-4 px-5 py-4" data-tour="letter-editor">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-fg-muted">
          {letter.word_count} words · {letter.language === 'fr' ? 'French' : 'English'} · from CV v{letter.cv_version ?? '?'}
        </span>
        <span className="text-fg-subtle" aria-live="polite">
          {note}
        </span>
      </div>
      <Checks violations={letter.violations} />
      <div className="space-y-1.5">
        <Label htmlFor="letter-salutation">Salutation</Label>
        <Input
          id="letter-salutation"
          value={salutation}
          disabled={readOnly}
          onChange={(e) => {
            setSalutation(e.target.value)
            queueSave({ salutation: e.target.value })
          }}
        />
      </div>
      {paragraphs.map((text, i) => (
        <div key={i} className="space-y-1.5">
          <Label htmlFor={`letter-p${i}`} className="flex items-center gap-2">
            Paragraph {i + 1}
            {letter.paragraphs[i]?.edited && (
              <ToneBadge tone="gray" dot={false}>
                edited
              </ToneBadge>
            )}
          </Label>
          <Textarea
            id={`letter-p${i}`}
            value={text}
            disabled={readOnly}
            className="min-h-28 [field-sizing:content] leading-relaxed"
            onChange={(e) => {
              const next = paragraphs.map((p, j) => (j === i ? e.target.value : p))
              setParagraphs(next)
              queueSave({ paragraphs: next })
            }}
          />
        </div>
      ))}
      <div className="space-y-1.5">
        <Label htmlFor="letter-ask">Closing ask</Label>
        <Input
          id="letter-ask"
          value={ask}
          disabled={readOnly}
          onChange={(e) => {
            setAsk(e.target.value)
            queueSave({ ask: e.target.value })
          }}
        />
        <p className="text-xs text-fg-subtle">Ends the last paragraph. Then, added by code: “{letter.closing}” and your name.</p>
      </div>
      <Sources letter={letter} />
    </div>
  )
}
