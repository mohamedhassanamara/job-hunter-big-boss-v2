import { RefreshCw, Sparkles, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** The model didn't answer after the retries. Never switches model by itself: you pick Retry
 * (same model) or "Generate with Claude" (this one time; the setting stays). */
export function GenerationFailed({
  what,
  message,
  onRetry,
  onClaude,
  onGemini,
  busy,
}: {
  what: 'CV' | 'email'
  message: string
  onRetry: () => void
  onClaude: () => void
  /** One click, this time only: the single Gemini key within its cap. Never automatic. */
  onGemini?: () => void
  busy?: boolean
}) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 border-b border-tone-red-border bg-danger-bg px-5 py-2.5 text-sm text-danger-fg" data-tour="generation-failed">
      <TriangleAlert className="size-4 shrink-0" />
      <p className="min-w-0 flex-1">
        <span className="font-medium">The {what} draft failed.</span> <span className="text-fg-muted">{message}</span>
      </p>
      <Button size="sm" variant="secondary" onClick={onRetry} disabled={busy}>
        <RefreshCw className={busy ? 'animate-spin' : undefined} />
        Retry
      </Button>
      {onGemini && (
        <Button size="sm" variant="secondary" onClick={onGemini} disabled={busy}>
          <Sparkles />
          Generate with Gemini
        </Button>
      )}
      <Button size="sm" variant="secondary" onClick={onClaude} disabled={busy}>
        <Sparkles />
        Generate with Claude
      </Button>
    </div>
  )
}
