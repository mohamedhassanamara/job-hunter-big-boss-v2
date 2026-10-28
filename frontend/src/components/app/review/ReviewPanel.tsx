import { MessageSquareText, TriangleAlert, WandSparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { DraftReview } from '@/lib/types'

/** The reviewer's feedback on a draft: advice only. It never blocks anything; "Apply suggestion"
 * is optional and replaces the draft text with the reviewer's revision. */
export function ReviewPanel({
  review,
  stale,
  onApply,
  compact = false,
}: {
  review: DraftReview
  /** The text changed since this review. */
  stale: boolean
  onApply?: (revisedBody: string) => void
  compact?: boolean
}) {
  const revised = review.revised_body.trim()
  return (
    <div data-tour="outreach-review" className="space-y-2 rounded-md border border-border bg-surface px-3 py-2 text-sm">
      <p className="flex items-center gap-2 text-xs font-medium text-fg-subtle">
        <MessageSquareText className="size-3.5" />
        Review{review.model ? ` · ${review.model}` : ''}
        {stale && <span className="font-normal text-warning-fg">· the text changed since: review it again to approve</span>}
      </p>
      {review.error ? (
        <p className="text-xs text-warning-fg">The reviewer couldn’t answer ({review.error}). You can still approve.</p>
      ) : (
        <>
          {review.feedback && <p className={compact ? 'text-xs whitespace-pre-line' : 'whitespace-pre-line'}>{review.feedback}</p>}
          {review.suggestions && (
            <p className={compact ? 'text-xs text-fg-muted' : 'text-fg-muted'}>
              <span className="font-medium text-fg">Suggestion: </span>
              {review.suggestions}
            </p>
          )}
          {review.has_unverified_claims && (
            <p className="flex items-start gap-1.5 text-xs text-warning-fg">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
              Some statements may not be backed by your experience or the listing. Informational: it doesn’t block approval.
            </p>
          )}
          {onApply && revised && !stale && (
            <Button size="xs" variant="secondary" onClick={() => onApply(revised)}>
              <WandSparkles />
              Apply suggestion
            </Button>
          )}
        </>
      )}
    </div>
  )
}
