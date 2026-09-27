import { ChevronDown, CircleAlert, Eye, EyeOff, TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Textarea } from '@/components/ui/input'
import { Tooltip } from '@/components/ui/tooltip'
import type { CVPatchInput, CVUsage, CVUsageEntry, CVVersion, ReadinessItem } from '@/lib/types'
import { cn } from '@/lib/utils'

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

      <Section title="Summary">
        <EditableText
          key={usage.summary.text}
          value={usage.summary.text}
          readOnly={readOnly}
          onSave={(text) => onPatch({ text: { summary: text } })}
          rows={4}
        />
        {usage.summary.text !== usage.summary.short && usage.summary.short && (
          <p className="mt-1 text-2xs text-fg-subtle">Short version (used when the page is tight): {usage.summary.short}</p>
        )}
      </Section>

      <Section title="Experience" hint="Every role stays on the CV (no gaps); choose which bullets show.">
        {usage.roles.map((entry) => (
          <Entry key={entry.key} entry={entry} readOnly={readOnly || busy} onToggle={toggle} onEdit={(key, text) => onPatch({ text: { [key]: text } })} />
        ))}
      </Section>

      {usage.projects.length > 0 && (
        <Section title="Projects" hint="Projects can be left out entirely.">
          {usage.projects.map((entry) => (
            <Entry key={entry.key} entry={entry} readOnly={readOnly || busy} entryToggle onToggle={toggle} onEdit={(key, text) => onPatch({ text: { [key]: text } })} />
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

function Violations({ version }: { version: CVVersion }) {
  const [open, setOpen] = useState(true)
  const items = version.violations
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
}: {
  entry: CVUsageEntry
  readOnly: boolean
  entryToggle?: boolean
  onToggle: (key: string, shown: boolean) => void
  onEdit: (key: string, text: string) => void
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
                {b.source && b.source !== b.text && (
                  <Tooltip content={<span className="block max-w-80">Source: {b.source}</span>}>
                    <span className="text-2xs text-fg-subtle underline decoration-dotted underline-offset-2">reworded</span>
                  </Tooltip>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
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
function EditableText({ value, readOnly, onSave, rows = 1, muted = false }: { value: string; readOnly: boolean; onSave: (t: string) => void; rows?: number; muted?: boolean }) {
  const [text, setText] = useState(value)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  if (readOnly) return <p className={cn('text-sm leading-5', muted ? 'text-fg-subtle' : 'text-fg')}>{value}</p>
  return (
    <Textarea
      value={text}
      rows={rows}
      onChange={(e) => {
        const next = e.target.value
        setText(next)
        window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => {
          if (next.trim() && next !== value) onSave(next.trim())
        }, 900)
      }}
      className="field-sizing-content min-h-8 resize-none border-transparent bg-transparent px-1 py-0.5 text-sm leading-5 shadow-none hover:border-border focus-visible:border-primary"
    />
  )
}
