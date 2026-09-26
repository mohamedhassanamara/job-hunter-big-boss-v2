import { CircleCheck, TriangleAlert } from 'lucide-react'
import { useLayoutEffect, useRef, useState } from 'react'
import type { CVContent, CVEntry } from '@/lib/types'
import { cn } from '@/lib/utils'

// A4 at 96dpi. The preview lays out at real size, then scales to fit the pane.
const PAGE_W = 794
const PAGE_H = 1123

export type PageFit = 'fits' | 'overflow' | 'sparse'

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mt-4 mb-1.5 border-b border-paper-rule pb-0.5 text-[11px] font-semibold tracking-[0.08em] text-paper-accent uppercase">
      {children}
    </h3>
  )
}

function Entry({ e }: { e: CVEntry }) {
  return (
    <div className="mb-2">
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-[12px] font-semibold">
          {e.title}
          {e.org && <span className="font-normal text-paper-muted"> · {e.org}</span>}
        </p>
        {e.dates && <p className="shrink-0 text-[10.5px] text-paper-muted">{e.dates}</p>}
      </div>
      {e.bullets.length > 0 && (
        <ul className="mt-0.5 ml-3.5 list-disc space-y-0.5 text-[11px] leading-[1.4] marker:text-paper-muted">
          {e.bullets.filter(Boolean).map((b, i) => (
            <li key={i}>{b}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Phase 0 stand-in for the compiled PDF: renders the structured content on an A4 sheet and
 * measures whether it fits one page (the real check comes from pdflatex's page count later).
 */
export function CVPreview({ content, onFit }: { content: CVContent; onFit?: (fit: PageFit) => void }) {
  const frame = useRef<HTMLDivElement>(null)
  const page = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.6)
  const [fit, setFit] = useState<PageFit>('fits')

  useLayoutEffect(() => {
    const el = frame.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setScale(Math.min(1, entry.contentRect.width / PAGE_W)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useLayoutEffect(() => {
    const h = page.current?.scrollHeight ?? 0
    const next: PageFit = h > PAGE_H + 1 ? 'overflow' : h < PAGE_H * 0.82 ? 'sparse' : 'fits'
    setFit(next)
    onFit?.(next)
  }, [content, onFit])

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-fg-subtle">Preview · A4 (placeholder for the compiled PDF)</span>
        <span
          data-tour="cv-fit"
          className={cn(
            'inline-flex items-center gap-1 font-medium',
            fit === 'fits' ? 'text-success-fg' : 'text-warning-fg',
          )}
        >
          {fit === 'fits' ? <CircleCheck className="size-3.5" /> : <TriangleAlert className="size-3.5" />}
          {fit === 'fits' ? '1 page, well filled' : fit === 'overflow' ? 'Overflows one page' : 'Too much white space'}
        </span>
      </div>
      <div ref={frame} className="w-full">
        <div
          className="relative overflow-hidden rounded-sm bg-paper shadow-lg ring-1 ring-border"
          style={{ height: PAGE_H * scale }}
        >
          <div
            ref={page}
            className="absolute top-0 left-0 origin-top-left px-[52px] py-[44px] font-sans text-paper-fg"
            style={{ width: PAGE_W, transform: `scale(${scale})` }}
          >
            <h1 className="text-[24px] leading-tight font-semibold tracking-tight">{content.name}</h1>
            <p className="text-[13px] font-medium text-paper-accent">{content.headline}</p>
            <p className="mt-1 text-[10.5px] text-paper-muted">{content.contact.join('  ·  ')}</p>
            {content.summary && (
              <>
                <SectionTitle>Summary</SectionTitle>
                <p className="text-[11px] leading-[1.45]">{content.summary}</p>
              </>
            )}
            {content.experience.length > 0 && (
              <>
                <SectionTitle>Experience</SectionTitle>
                {content.experience.map((e, i) => (
                  <Entry key={i} e={e} />
                ))}
              </>
            )}
            {content.projects.length > 0 && (
              <>
                <SectionTitle>Projects</SectionTitle>
                {content.projects.map((e, i) => (
                  <Entry key={i} e={e} />
                ))}
              </>
            )}
            {content.skills.length > 0 && (
              <>
                <SectionTitle>Skills</SectionTitle>
                <div className="space-y-0.5 text-[11px]">
                  {content.skills.map((s, i) => (
                    <p key={i}>
                      <span className="font-semibold">{s.group}: </span>
                      {s.items.join(', ')}
                    </p>
                  ))}
                </div>
              </>
            )}
            {content.education.length > 0 && (
              <>
                <SectionTitle>Education</SectionTitle>
                {content.education.map((e, i) => (
                  <Entry key={i} e={e} />
                ))}
              </>
            )}
          </div>
          {fit === 'overflow' && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-linear-to-t from-danger-bg to-transparent" />
          )}
        </div>
      </div>
    </div>
  )
}
