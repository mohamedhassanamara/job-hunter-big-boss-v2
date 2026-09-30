import { CircleX, Copy, MessageSquareText, Plus, Sparkles, Trash2, TriangleAlert, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Section } from '@/components/app/PageHeader'
import { EmptyState } from '@/components/app/states'
import { Button } from '@/components/ui/button'
import { Input, Textarea } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip } from '@/components/ui/tooltip'
import { useAnswerQuestions, useAnswers, useDeleteAnswer, usePatchAnswer } from '@/lib/queries/letters'
import type { ApplicationAnswer, JobDetail } from '@/lib/types'
import { cn } from '@/lib/utils'

interface NewQuestion {
  question: string
  limit: string
}

const empty = (): NewQuestion => ({ question: '', limit: '' })

function AnswerCard({ answer, onDelete }: { answer: ApplicationAnswer; onDelete: () => void }) {
  const patch = usePatchAnswer()
  const [text, setText] = useState(answer.answer)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved'>('idle')
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const over = answer.char_limit != null && text.length > answer.char_limit
  const save = (value: string) => {
    setSaveState('saving')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(
      () =>
        patch.mutate(
          { id: answer.id, answer: value },
          { onSuccess: () => setSaveState('saved'), onError: (e) => (setSaveState('idle'), toast.error(`Couldn't save: ${e.message}`)) },
        ),
      700,
    )
  }
  return (
    <li className="space-y-2 border-b border-border px-4 py-3 last:border-b-0">
      <div className="flex items-start gap-2">
        <p className="flex-1 text-sm font-medium">{answer.question}</p>
        <Tooltip content="Copy the answer">
          <Button
            size="icon-sm"
            variant="ghost"
            aria-label="Copy the answer"
            onClick={() => navigator.clipboard.writeText(text).then(() => toast.success('Answer copied'), () => toast.error("Couldn't copy"))}
          >
            <Copy />
          </Button>
        </Tooltip>
        <Tooltip content="Delete">
          <Button size="icon-sm" variant="ghost" aria-label="Delete the answer" onClick={onDelete}>
            <Trash2 />
          </Button>
        </Tooltip>
      </div>
      <Textarea
        value={text}
        aria-label={`Answer to ${answer.question}`}
        className="min-h-20 [field-sizing:content]"
        onChange={(e) => {
          setText(e.target.value)
          save(e.target.value)
        }}
      />
      <div className="flex items-center gap-3 text-xs">
        <span className={cn('tabular-nums', over ? 'font-medium text-danger-fg' : 'text-fg-subtle')}>
          {answer.char_limit != null ? `${text.length}/${answer.char_limit} characters` : `${text.length} characters`}
        </span>
        {answer.edited && <span className="text-fg-subtle">edited</span>}
        <span className="ml-auto text-fg-subtle" aria-live="polite">
          {saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? 'All changes saved' : ''}
        </span>
      </div>
      {answer.violations.length > 0 && (
        <ul className="space-y-1">
          {answer.violations.map((v, i) => (
            <li key={i} className={cn('flex items-start gap-2 text-xs', v.severity === 'error' ? 'text-danger-fg' : 'text-warning-fg')}>
              {v.severity === 'error' ? <CircleX className="mt-px size-3.5 shrink-0" /> : <TriangleAlert className="mt-px size-3.5 shrink-0" />}
              {v.message}
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

/** Web apply: answers to the application form's questions, grounded in the approved CV, with the
 * form's character limits (checked, never cut), saved on the job. */
export function QuestionsSection({ job }: { job: JobDetail }) {
  const app = job.application
  const hasApprovedCv = job.cv_versions.some((v) => v.status === 'approved')
  const show = app.effective_route === 'web_apply' && hasApprovedCv
  const { data, isPending } = useAnswers(show ? app.id : NaN)
  const generate = useAnswerQuestions()
  const remove = useDeleteAnswer()
  const [rows, setRows] = useState<NewQuestion[]>([empty()])
  const [adding, setAdding] = useState(false)
  const [hidden, setHidden] = useState<number[]>([])
  if (!show) return null
  const saved = (data ?? []).filter((a) => !hidden.includes(a.id))
  const ready = rows.filter((r) => r.question.trim())

  const submit = () => {
    const t = toast.loading(`Answering ${ready.length} question${ready.length > 1 ? 's' : ''} with Claude…`)
    generate.mutate(
      { appId: app.id, questions: ready.map((r) => ({ question: r.question.trim(), char_limit: r.limit ? Number(r.limit) : null })) },
      {
        onSuccess: (answers) => {
          const problems = answers.filter((a) => a.violations.some((v) => v.severity === 'error')).length
          toast[problems ? 'warning' : 'success'](problems ? `${problems} answer${problems > 1 ? 's' : ''} to fix` : 'Answers ready: review and copy them', { id: t })
          setRows([empty()])
          setAdding(false)
        },
        onError: (e) => toast.error(e.message, { id: t }),
      },
    )
  }

  // Deleting waits 8 seconds so it can be undone.
  const onDelete = (a: ApplicationAnswer) => {
    setHidden((h) => [...h, a.id])
    const timeout = window.setTimeout(() => remove.mutate({ id: a.id, appId: app.id }, { onError: (e) => toast.error(e.message) }), 8000)
    toast('Answer deleted', {
      duration: 8000,
      action: {
        label: 'Undo',
        onClick: () => {
          window.clearTimeout(timeout)
          setHidden((h) => h.filter((x) => x !== a.id))
        },
      },
    })
  }

  const form = (
    <div className="space-y-2 border-t border-border p-4 first:border-t-0">
      {rows.map((r, i) => (
        <div key={i} className="flex items-start gap-2">
          <Textarea
            value={r.question}
            placeholder="Paste a question from the form"
            aria-label={`Question ${i + 1}`}
            className="min-h-10 flex-1 [field-sizing:content]"
            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, question: e.target.value } : x)))}
          />
          <Input
            type="number"
            min={20}
            value={r.limit}
            placeholder="Max chars"
            aria-label={`Character limit for question ${i + 1}`}
            className="w-28"
            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, limit: e.target.value } : x)))}
          />
          {rows.length > 1 && (
            <Button size="icon" variant="ghost" aria-label="Remove question" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
              <X />
            </Button>
          )}
        </div>
      ))}
      <div className="flex items-center gap-2 pt-1">
        <Button size="sm" variant="ghost" onClick={() => setRows([...rows, empty()])} disabled={rows.length >= 10}>
          <Plus />
          Add question
        </Button>
        <span className="flex-1" />
        {adding && (
          <Button size="sm" variant="ghost" onClick={() => (setAdding(false), setRows([empty()]))}>
            Cancel
          </Button>
        )}
        <Button size="sm" onClick={submit} disabled={!ready.length || generate.isPending}>
          <Sparkles className={generate.isPending ? 'animate-pulse' : undefined} />
          {generate.isPending ? 'Answering…' : 'Answer with AI'}
        </Button>
      </div>
    </div>
  )

  return (
    <Section
      title="Application questions"
      action={
        saved.length > 0 &&
        !adding && (
          <Button size="xs" variant="ghost" onClick={() => setAdding(true)}>
            <Plus />
            Add questions
          </Button>
        )
      }
    >
      <div data-tour="job-questions">
        {isPending ? (
          <Skeleton className="m-4 h-16" />
        ) : saved.length === 0 && !adding ? (
          <EmptyState
            compact
            icon={MessageSquareText}
            title="No questions yet"
            description="Paste the form's questions (with their character limits): answers come from your approved CV, in the listing's language, and are saved here."
            action={
              <Button size="sm" onClick={() => setAdding(true)}>
                <Plus />
                Add questions
              </Button>
            }
          />
        ) : (
          <>
            {saved.length > 0 && (
              <ul>
                {saved.map((a) => (
                  <AnswerCard key={a.id} answer={a} onDelete={() => onDelete(a)} />
                ))}
              </ul>
            )}
            {(adding || saved.length === 0) && form}
          </>
        )}
      </div>
    </Section>
  )
}
