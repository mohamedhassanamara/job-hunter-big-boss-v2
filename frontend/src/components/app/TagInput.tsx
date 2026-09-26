import { X } from 'lucide-react'
import { useState } from 'react'

/** Token input: Enter or comma adds, Backspace on empty removes the last token. */
export function TagInput({
  tags,
  onChange,
  placeholder = 'spark, dbt, llm… (Enter to add)',
  lowercase = true,
}: {
  tags: string[]
  onChange: (t: string[]) => void
  placeholder?: string
  lowercase?: boolean
}) {
  const [draft, setDraft] = useState('')
  const add = (raw: string) => {
    const values = raw
      .split(',')
      .map((t) => (lowercase ? t.trim().toLowerCase() : t.trim()))
      .filter((t) => t && !tags.includes(t))
    if (values.length) onChange([...tags, ...values])
    setDraft('')
  }
  return (
    <div className="flex min-h-8 flex-wrap items-center gap-1.5 rounded-md border border-border-strong bg-surface px-1.5 py-1 focus-within:border-primary focus-within:ring-3 focus-within:ring-ring">
      {tags.map((t) => (
        <span key={t} className="inline-flex h-5 items-center gap-1 rounded-sm bg-surface-hover pr-0.5 pl-1.5 text-xs">
          {t}
          <button
            type="button"
            onClick={() => onChange(tags.filter((x) => x !== t))}
            className="rounded-sm p-0.5 text-fg-subtle hover:text-fg"
            aria-label={`Remove ${t}`}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            add(draft)
          } else if (e.key === 'Backspace' && !draft && tags.length) {
            onChange(tags.slice(0, -1))
          }
        }}
        onBlur={() => draft && add(draft)}
        placeholder={tags.length ? '' : placeholder}
        className="h-6 min-w-24 flex-1 bg-transparent px-1 text-sm outline-none placeholder:text-fg-subtle"
      />
    </div>
  )
}
