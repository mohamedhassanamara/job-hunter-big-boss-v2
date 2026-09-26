import { cn } from '@/lib/utils'

/**
 * Renders the small markdown subset job descriptions use (## headings, - bullets, paragraphs)
 * as React elements. No HTML injection.
 */
export function Prose({ text, className }: { text: string; className?: string }) {
  const blocks: React.ReactNode[] = []
  let bullets: string[] = []
  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`} className="ml-4 list-disc space-y-1 marker:text-fg-subtle">
          {bullets.map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>,
      )
      bullets = []
    }
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (line.startsWith('- ')) {
      bullets.push(line.slice(2))
      continue
    }
    flush()
    if (!line) continue
    if (line.startsWith('#')) {
      blocks.push(
        <h3 key={blocks.length} className="pt-2 text-sm font-semibold text-fg first:pt-0">
          {line.replace(/^#+\s*/, '')}
        </h3>,
      )
    } else {
      blocks.push(<p key={blocks.length}>{line}</p>)
    }
  }
  flush()
  return <div className={cn('space-y-2 text-base text-fg-muted', className)}>{blocks}</div>
}
