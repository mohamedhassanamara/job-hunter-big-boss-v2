import { Bot, Copy, LoaderCircle, SendHorizontal, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Prose } from '@/components/app/Prose'
import { ErrorState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { Tooltip } from '@/components/ui/tooltip'
import { useAskCopilot, useCopilotStatus } from '@/lib/queries/copilot'
import type { CopilotMessage, CopilotThreadDetail } from '@/lib/types'
import { cn } from '@/lib/utils'

function Answer({ text, message }: { text: string; message?: CopilotMessage }) {
  const copy = () =>
    navigator.clipboard.writeText(text).then(
      () => toast.success('Copied'),
      () => toast.error("Couldn't copy"),
    )
  return (
    <div className="group space-y-2">
      <div className="flex items-start gap-2">
        <Bot className="mt-1 size-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1 text-sm">{text ? <Prose text={text} /> : <span className="text-fg-subtle">Thinking…</span>}</div>
        {message && text && (
          <Tooltip content="Copy">
            <Button size="icon-sm" variant="ghost" aria-label="Copy the answer" onClick={copy} className="opacity-60 group-hover:opacity-100">
              <Copy />
            </Button>
          </Tooltip>
        )}
      </div>
      {message && message.warnings.length > 0 && (
        <ul className="ml-6 space-y-0.5 rounded-md bg-warning-bg px-3 py-2 text-xs text-warning-fg">
          {message.warnings.map((w, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <TriangleAlert className="mt-px size-3.5 shrink-0" />
              {w.message}
            </li>
          ))}
        </ul>
      )}
      {message?.model && (
        <p className="ml-6 text-2xs text-fg-subtle">
          {message.model}
          {message.duration_ms ? ` · ${Math.round(message.duration_ms / 1000)}s` : ''}
        </p>
      )}
    </div>
  )
}

/** A Copilot conversation: history, the streamed answer, starter questions and the input. */
export function CopilotChat({ thread, placeholder }: { thread: CopilotThreadDetail; placeholder: string }) {
  const status = useCopilotStatus()
  const { ask, streaming, error, pending } = useAskCopilot()
  const [question, setQuestion] = useState('')
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => end.current?.scrollIntoView({ block: 'end' }), [thread.messages.length, streaming?.answer])

  const send = (q: string) => {
    const text = q.trim()
    if (!text || pending) return
    setQuestion('')
    void ask(thread.id, text)
  }
  const down = status.data && !status.data.ok

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4" data-tour="copilot-messages">
        {down && (
          <ErrorState error={new Error(`${status.data!.message} The Copilot uses the local model (${status.data!.model}).`)} onRetry={() => status.refetch()} />
        )}
        {thread.messages.length === 0 && !streaming && (
          <div className="space-y-2" data-tour="copilot-starters">
            <p className="text-sm text-fg-muted">
              Ask anything about {thread.application_id ? 'this job' : 'your search'}. It answers from your data (listing, fit, CV, letter, experience) and
              never changes anything.
            </p>
            <div className="flex flex-wrap gap-2">
              {thread.starters.map((s) => (
                <Button key={s} size="sm" variant="secondary" onClick={() => send(s)} disabled={pending || down}>
                  {s}
                </Button>
              ))}
            </div>
          </div>
        )}
        {thread.messages.map((m) =>
          m.role === 'user' ? (
            <p key={m.id} className="ml-auto w-fit max-w-[85%] rounded-lg bg-surface-selected px-3 py-2 text-sm whitespace-pre-wrap">
              {m.content}
            </p>
          ) : (
            <Answer key={m.id} text={m.content} message={m} />
          ),
        )}
        {streaming && (
          <>
            <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-surface-selected px-3 py-2 text-sm whitespace-pre-wrap">{streaming.question}</p>
            <Answer text={streaming.answer} />
          </>
        )}
        {error && <p className="text-sm text-danger-fg">{error}</p>}
        <div ref={end} />
      </div>
      <div className="border-t border-border p-3" data-tour="copilot-input">
        <div className="flex items-end gap-2">
          <Textarea
            value={question}
            placeholder={placeholder}
            aria-label="Ask the Copilot"
            className={cn('max-h-40 min-h-10 flex-1 [field-sizing:content]')}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send(question)
              }
            }}
          />
          <Button variant="default" onClick={() => send(question)} disabled={!question.trim() || pending || down} aria-label="Send">
            {pending ? <LoaderCircle className="animate-spin" /> : <SendHorizontal />}
          </Button>
        </div>
        <p className="mt-1.5 text-2xs text-fg-subtle">
          Local model ({status.data?.model ?? '…'}) · Enter to send, Shift+Enter for a new line · facts about you come only from your experience
        </p>
      </div>
    </div>
  )
}
