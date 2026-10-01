import { Bookmark, Copy } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { bookmarkletHref } from '@/features/linkedin/bookmarklet'

/** "Save to Job Hunter": drag it to the bookmarks bar, then click it on a LinkedIn job page.
 * (React refuses javascript: links in JSX, so the href is set on the element.) */
export function BookmarkInstall({ compact = false }: { compact?: boolean }) {
  const ref = useRef<HTMLAnchorElement>(null)
  const href = bookmarkletHref(window.location.origin)
  useEffect(() => {
    ref.current?.setAttribute('href', href)
  }, [href])
  return (
    <div className="space-y-3" data-tour="linkedin-bookmark">
      <div className="flex flex-wrap items-center gap-3">
        <a
          ref={ref}
          onClick={(e) => {
            e.preventDefault()
            toast('Drag this button to your bookmarks bar', { description: 'Then click it on a LinkedIn job page.' })
          }}
          className="inline-flex h-8 cursor-grab items-center gap-2 rounded-md border border-primary bg-primary-subtle px-3 text-sm font-medium text-fg active:cursor-grabbing"
          title="Drag me to the bookmarks bar"
        >
          <Bookmark className="size-4 text-primary" />
          Save to Job Hunter
        </a>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => navigator.clipboard.writeText(href).then(() => toast.success('Bookmark code copied', { description: 'Create a bookmark and paste it as its URL.' }))}
        >
          <Copy />
          Copy the bookmark code
        </Button>
      </div>
      {!compact && (
        <ol className="list-decimal space-y-1 pl-5 text-sm text-fg-muted">
          <li>Show the bookmarks bar (⌘⇧B in Chrome) and drag “Save to Job Hunter” onto it.</li>
          <li>On LinkedIn, open a job (its own page, or a job selected in the search results) and click “See more” on the description.</li>
          <li>Click the bookmark: a small Job Hunter window opens with what it read. Check the fields, then save: the job is scored right away.</li>
          <li>It reads only the page you're on, in your browser. The app never visits LinkedIn itself. If your browser blocks the window, allow pop-ups for linkedin.com.</li>
        </ol>
      )}
    </div>
  )
}
