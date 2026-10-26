import { ChevronDown, CircleAlert, Eye, EyeOff, History, TriangleAlert, Undo2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Tooltip } from '@/components/ui/tooltip'
import { useRestoreSummary, useSummaryCheck } from '@/lib/queries/workflow'
import type { CVPatchInput, CVUsage, CVUsageEntry, CVVersion, CVViolation, ReadinessItem } from '@/lib/types'
import { cn } from '@/lib/utils'
import { wordDiff } from '@/lib/wordDiff'

/** Left side of CV Studio: what the CV uses from your experience pool and what it leaves out.
 * Toggling or editing re-fits the page in code (no Claude call). */
export function CVContentPanel({
  version,
  usage,
  readiness,
  readOnly,
  busy,
  onPatch,
}: {
  version: CVVersion
  usage: CVUsage
  readiness: ReadinessItem[]
  readOnly: boolean
  busy: boolean
  onPatch: (patch: CVPatchInput) => void
}) {
  const forceIn = new Set(usage.force_in)
  const forceOut = new Set(usage.force_out)

  const toggle = (key: string, shown: boolean) => {
    const nextIn = new Set(forceIn)
    const nextOut = new Set(forceOut)
    if (shown) {
      nextIn.delete(key)
      nextOut.add(key)
    } else {
      nextOut.delete(key)
      nextIn.add(key)
    }
    onPatch({ force_in: [...nextIn], force_out: [...nextOut] })
  }

  return (
    <div className="space-y-5 px-5 py-4">
      {readiness.length > 0 && (
        <div className="space-y-1.5">
          {readiness.map((r) => (
            <p key={r.key} className={cn('flex items-start gap-2 rounded-md px-3 py-2 text-xs', r.severity === 'blocker' ? 'bg-danger-bg text-danger-fg' : 'bg-warning-bg text-warning-fg')}>
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              {r.message}
            </p>
          ))}
        </div>
      )}
      <Violations version={version} />

      <Section title="Summary" hint="Each sentence cites the experience it comes from (hover). The checks below are information: they never stop you approving.">
        <SummaryBlock version={version} usage={usage} readOnly={readOnly} onSave={(text) => onPatch({ text: { summary: text } })} />
      </Section>

      <Section title="Experience" hint="Every role stays on the CV (no gaps); choose which bullets show. Bullets may be lightly adapted to the job; your pool text is never changed.">
        <label className="flex items-center gap-2 text-xs text-fg-muted" data-tour="original-only">
          <Switch
            checked={usage.original_only}
            disabled={readOnly || busy}
            onCheckedChange={(original_only) => onPatch({ original_only })}
            aria-label="Use original bullets only"
          />
          Use original bullets only
          {usage.tailoring && (
            <span className="ml-auto text-2xs text-fg-subtle">
              {usage.tailoring.adapted} adapted · {usage.tailoring.original} original
              {usage.tailoring.fallbacks.length > 0 && ` · ${usage.tailoring.fallbacks.length} refused by the checks`}
            </span>
          )}
        </label>
        {usage.roles.map((entry) => (
          <Entry key={entry.key} entry={entry} readOnly={readOnly || busy} onToggle={toggle} onEdit={(key, text) => onPatch({ text: { [key]: text } })} onRevert={(key, on) => onPatch({ revert: on ? [...usage.revert, key] : usage.revert.filter((k) => k !== key) })} />
        ))}
      </Section>

      {usage.projects.length > 0 && (
        <Section title="Projects" hint="Projects can be left out entirely.">
          {usage.projects.map((entry) => (
            <Entry key={entry.key} entry={entry} readOnly={readOnly || busy} entryToggle onToggle={toggle} onEdit={(key, text) => onPatch({ text: { [key]: text } })} onRevert={(key, on) => onPatch({ revert: on ? [...usage.revert, key] : usage.revert.filter((k) => k !== key) })} />
          ))}
        </Section>
      )}

      {usage.certifications.length > 0 && (
        <Section title="Certifications">
          <div className="space-y-1">
            {usage.certifications.map((c) => (
              <ToggleRow key={c.key} shown={c.shown} disabled={readOnly || busy} onToggle={() => toggle(c.key, c.shown)}>
                <span className="font-medium">{c.title}</span>
                {c.org && <span className="text-fg-muted"> · {c.org}</span>}
              </ToggleRow>
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}

const KIND_LABEL: Record<string, string> = {
  job: 'Role', project: 'Project', skill: 'Skills', summary: 'Your snippet', education: 'Education',
  certification: 'Certification', volunteering: 'Volunteering',
}

function CitedSummary({ usage }: { usage: CVUsage }) {
  const { sentences, grounding, edited, feedback } = usage.summary
  if (!sentences.length) return null
  return (
    <div className="mb-1.5 rounded-md bg-bg-subtle px-2.5 py-2 text-xs leading-5">
      <p className="text-fg-muted">
        {sentences.map((s, i) => (
          <Tooltip
            key={i}
            content={
              <span className="block max-w-80 space-y-0.5">
                <span className="block font-medium">Based on</span>
                {s.citations.map((c) => (
                  <span key={c.id} className="block text-fg-muted">
                    {KIND_LABEL[c.kind] ?? c.kind}: {c.title}
                  </span>
                ))}
              </span>
            }
          >
            <span className="cursor-help underline decoration-border-strong decoration-dotted underline-offset-2 hover:bg-primary-subtle">{s.text}</span>
          </Tooltip>
        )).reduce<React.ReactNode[]>((acc, el, i) => (i ? [...acc, ' ', el] : [el]), [])}
      </p>
      <p className="mt-1 text-2xs text-fg-subtle">
        {edited ? 'You edited the summary below; these citations are for the generated version.' : 'Generated from the cited experience.'}
        {!edited && feedback && ` Written with your feedback: “${feedback}”.`}
        {grounding && grounding.attempts > 1 && ` Regenerated once automatically after the checks found problems.`}
      </p>
    </div>
  )
}

/** The summary: generated text and its citations, an editor with live checks (information only),
 * and the history of earlier summaries with the feedback that produced them. */
function SummaryBlock({ version, usage, readOnly, onSave }: { version: CVVersion; usage: CVUsage; readOnly: boolean; onSave: (text: string) => void }) {
  const [live, setLive] = useState(usage.summary.text)
  const [settled, setSettled] = useState(usage.summary.text)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const type = (text: string) => {
    setLive(text)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setSettled(text), 450)
  }
  const check = useSummaryCheck(version.id, settled, true)
  const warnings: CVViolation[] = check.data?.warnings ?? version.violations.filter((v) => v.where === 'summary')

  return (
    <>
      <CitedSummary usage={usage} />
      <EditableText key={usage.summary.text} value={usage.summary.text} readOnly={readOnly} onSave={onSave} onType={type} rows={4} summary />
      {usage.summary.text !== usage.summary.short && usage.summary.short && (
        <p className="mt-1 text-2xs text-fg-subtle">Short version (used when the page is tight): {usage.summary.short}</p>
      )}
      <SummaryWarnings warnings={warnings} pending={check.isFetching || live !== settled} />
      <SummaryHistory version={version} usage={usage} readOnly={readOnly} />
    </>
  )
}

function highlight(message: string, phrase: string | null | undefined) {
  const at = phrase ? message.indexOf(phrase) : -1
  if (!phrase || at < 0) return message
  return (
    <>
      {message.slice(0, at)}
      <mark className="rounded-sm bg-warning-bg px-0.5 text-warning-fg">{phrase}</mark>
      {message.slice(at + phrase.length)}
    </>
  )
}

function SummaryWarnings({ warnings, pending }: { warnings: CVViolation[]; pending: boolean }) {
  if (!warnings.length) return pending ? <p className="mt-1.5 text-2xs text-fg-subtle">Checking…</p> : null
  return (
    <div className="mt-1.5 rounded-md border border-border px-3 py-2" aria-live="polite">
      <p className="mb-1 flex items-center gap-1.5 text-2xs font-medium text-fg-muted">
        <TriangleAlert className="size-3 text-warning-dot" />
        {warnings.length} summary warning{warnings.length === 1 ? '' : 's'}
        <span className="font-normal text-fg-subtle">· information only, you can still approve{pending ? ' · checking…' : ''}</span>
      </p>
      <ul className="space-y-1 text-xs">
        {warnings.map((w, i) => (
          <li key={`${w.type}-${i}`} className="flex gap-2">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-warning-dot" />
            <span>
              {w.phrase && !w.message.includes(w.phrase) && <mark className="mr-1 rounded-sm bg-warning-bg px-0.5 text-warning-fg">{w.phrase}</mark>}
              {highlight(w.rule ?? w.message, w.phrase)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function SummaryHistory({ version, usage, readOnly }: { version: CVVersion; usage: CVUsage; readOnly: boolean }) {
  const [open, setOpen] = useState(false)
  const restore = useRestoreSummary()
  const history = [...usage.summary.history].reverse()
  if (!history.length) return null
  const canRestore = version.status === 'draft' && !readOnly
  return (
    <div className="mt-1.5">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex items-center gap-1.5 text-2xs text-fg-subtle hover:text-fg">
        <History className="size-3" />
        Earlier summaries ({history.length})
        <ChevronDown className={cn('size-3 transition-transform duration-120', !open && '-rotate-90')} />
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1.5">
          {history.map((h) => (
            <li key={h.index} className="rounded-md bg-bg-subtle px-2.5 py-2 text-xs leading-5">
              <p className="text-fg-muted">{h.text}</p>
              <p className="mt-1 flex items-center gap-2 text-2xs text-fg-subtle">
                <span className="min-w-0 flex-1 truncate">
                  {h.kind === 'edited' ? 'Typed by you' : 'Generated'}
                  {h.feedback ? ` · you asked: “${h.feedback}”` : ''}
                </span>
                <Button
                  size="xs"
                  variant="ghost"
                  disabled={!canRestore || restore.isPending}
                  onClick={() => restore.mutate({ cvId: version.id, index: h.index }, { onSuccess: () => toast.success('Earlier summary restored'), onError: (e) => toast.error(e.message) })}
                >
                  <Undo2 />
                  Use this
                </Button>
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Violations({ version }: { version: CVVersion }) {
  const [open, setOpen] = useState(true)
  const items = version.violations.filter((v) => v.where !== 'summary') // the summary's sit under it
  if (!items.length) return null
  const errors = items.filter((v) => v.severity === 'error').length
  return (
    <div className="rounded-lg border border-border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium"
        aria-expanded={open}
      >
        <CircleAlert className={cn('size-3.5', errors ? 'text-danger-dot' : 'text-warning-dot')} />
        {errors ? `${errors} check${errors === 1 ? '' : 's'} failed` : 'Worth a look'}
        <span className="font-normal text-fg-subtle">
          {' '}· facts are checked against your experience ({items.length})
        </span>
        <ChevronDown className={cn('ml-auto size-3.5 transition-transform duration-120', !open && '-rotate-90')} />
      </button>
      {open && (
        <ul className="space-y-1 border-t border-border px-3 py-2 text-xs">
          {items.map((v, i) => (
            <li key={i} className="flex gap-2">
              <span className={cn('mt-1 size-1.5 shrink-0 rounded-full', v.severity === 'error' ? 'bg-danger-dot' : 'bg-warning-dot')} />
              <span>
                <span className="text-fg-muted">{v.where}: </span>
                {v.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <div>
        <h3 className="text-xs font-semibold tracking-wide text-fg-muted uppercase">{title}</h3>
        {hint && <p className="text-2xs text-fg-subtle">{hint}</p>}
      </div>
      {children}
    </section>
  )
}

function Entry({
  entry,
  readOnly,
  entryToggle = false,
  onToggle,
  onEdit,
  onRevert,
}: {
  entry: CVUsageEntry
  readOnly: boolean
  entryToggle?: boolean
  onToggle: (key: string, shown: boolean) => void
  onEdit: (key: string, text: string) => void
  onRevert: (key: string, on: boolean) => void
}) {
  return (
    <div className={cn('rounded-lg border border-border bg-surface', !entry.shown && 'opacity-70')}>
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{entry.title}</p>
          {entry.org && <p className="truncate text-xs text-fg-muted">{entry.org}</p>}
        </div>
        {entry.relevance > 0 && (
          <Tooltip content="How relevant the generator judged this entry for the job (1–10)">
            <span className="text-2xs text-fg-subtle tabular-nums">rel. {entry.relevance}</span>
          </Tooltip>
        )}
        {entryToggle && (
          <ToggleButton shown={entry.shown} disabled={readOnly} onClick={() => onToggle(entry.key, entry.shown)} label={entry.title} />
        )}
      </div>
      {entry.bullets.length > 0 && (
        <ul className="space-y-1 border-t border-border px-3 py-2">
          {entry.bullets.map((b) => (
            <li key={b.key} className="flex items-start gap-2">
              <ToggleButton shown={b.shown} disabled={readOnly} onClick={() => onToggle(b.key, b.shown)} label="bullet" />
              <div className="min-w-0 flex-1">
                <EditableText key={b.text} value={b.text} readOnly={readOnly || !b.shown} onSave={(text) => onEdit(b.key, text)} muted={!b.shown} />
                {b.source && b.adapted && !b.manual && (
                  <BulletDiff original={b.source} adapted={b.text} poolId={b.pool_id} disabled={readOnly} onRevert={() => onRevert(b.key, true)} />
                )}
                {b.reverted && b.tailored_text && (
                  <p className="flex items-center gap-1.5 text-2xs text-fg-subtle">
                    Original wording ({b.pool_id}).
                    <button type="button" disabled={readOnly} className="underline decoration-dotted underline-offset-2 hover:text-fg disabled:opacity-40" onClick={() => onRevert(b.key, false)}>
                      Use the adapted wording
                    </button>
                  </p>
                )}
                {b.fallback && !b.reverted && !b.adapted && <p className="text-2xs text-fg-subtle">Adaptation refused ({b.fallback}): original used.</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** The bullet's change against your pool original (words removed struck through, added marked),
 * with a one-click return to the original. */
function BulletDiff({ original, adapted, poolId, disabled, onRevert }: { original: string; adapted: string; poolId: string; disabled: boolean; onRevert: () => void }) {
  return (
    <div className="mt-1 rounded-md bg-bg-subtle px-2 py-1.5 text-2xs leading-4 text-fg-muted" data-tour="bullet-diff">
      <p className="mb-0.5 flex items-center gap-2">
        <span className="font-medium text-fg-subtle">Adapted from pool bullet {poolId}</span>
        <Button type="button" size="xs" variant="ghost" className="ml-auto" disabled={disabled} onClick={onRevert}>
          <Undo2 />
          Revert to original
        </Button>
      </p>
      <p>
        {wordDiff(original, adapted).map((part, i) => (
          <span
            key={i}
            className={cn(
              part.kind === 'removed' && 'bg-danger-bg text-danger-fg line-through',
              part.kind === 'added' && 'bg-success-bg text-success-fg',
            )}
          >
            {part.text}
          </span>
        ))}
      </p>
    </div>
  )
}

function ToggleButton({ shown, disabled, onClick, label }: { shown: boolean; disabled: boolean; onClick: () => void; label: string }) {
  return (
    <Tooltip content={shown ? 'On the CV: click to leave out' : 'Left out: click to force in'}>
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-pressed={shown}
        aria-label={`${shown ? 'Leave out' : 'Force in'} ${label}`}
        className={cn('mt-0.5 rounded-sm p-0.5 disabled:opacity-40', shown ? 'text-primary' : 'text-fg-subtle hover:text-fg')}
      >
        {shown ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
      </button>
    </Tooltip>
  )
}

function ToggleRow({ shown, disabled, onToggle, children }: { shown: boolean; disabled: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <div className={cn('flex items-center gap-2 text-sm', !shown && 'opacity-70')}>
      <ToggleButton shown={shown} disabled={disabled} onClick={onToggle} label="item" />
      <span className="min-w-0 truncate">{children}</span>
    </div>
  )
}

/** Text that saves 900ms after typing stops (then the page re-fits). Callers key it by the saved
 * value, so a server-side change resets the draft text. */
function EditableText({ value, readOnly, onSave, onType, rows = 1, muted = false, summary = false }: { value: string; readOnly: boolean; onSave: (t: string) => void; onType?: (t: string) => void; rows?: number; muted?: boolean; summary?: boolean }) {
  const [text, setText] = useState(value)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  if (readOnly) return <p className={cn('text-sm leading-5', muted ? 'text-fg-subtle' : 'text-fg')}>{value}</p>
  return (
    <Textarea
      value={text}
      rows={rows}
      data-cv-summary={summary ? '' : undefined}
      onChange={(e) => {
        const next = e.target.value
        setText(next)
        onType?.(next)
        window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => {
          if (next.trim() && next !== value) onSave(next.trim())
        }, 900)
      }}
      className="field-sizing-content min-h-8 resize-none border-transparent bg-transparent px-1 py-0.5 text-sm leading-5 shadow-none hover:border-border focus-visible:border-primary"
    />
  )
}
