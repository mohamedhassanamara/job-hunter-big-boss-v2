import { ArrowUpRight, CircleCheck, Copy, FileText, Globe } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { EmptyState, ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { MarkAppliedDialog } from '@/components/app/tracking/TrackingDialogs'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { useListKeyboard } from '@/hooks/useListKeyboard'
import { apiUrl } from '@/lib/api'
import { countryName } from '@/lib/format'
import { useSettings } from '@/lib/queries/library'
import { useAnswers, useLetterStudio } from '@/lib/queries/letters'
import { useReadyToApply } from '@/lib/queries/tracking'
import { openListingAndCv } from '@/lib/tracking'
import type { ReadyItem } from '@/lib/types'
import { cn } from '@/lib/utils'

const pdfUrl = (r: ReadyItem) => apiUrl(`/cv/${r.cv_version_id}/pdf`, { download: true })
const letterUrl = (r: ReadyItem) => (r.letter_status === 'approved' && r.letter_id ? apiUrl(`/letters/${r.letter_id}/pdf`, { download: true }) : null)

const copy = (text: string, what: string) =>
  navigator.clipboard.writeText(text).then(() => toast.success(`${what} copied`), (e: Error) => toast.error(e.message))

/** Copy the approved cover letter, the form text and the verified answers of the selected job:
 * what you paste into the application form. Only fetched for the selected row. */
function CopyButtons({ appId }: { appId: number }) {
  const letters = useLetterStudio(appId)
  const answers = useAnswers(appId)
  const letter = letters.data?.letters.find((l) => l.status === 'approved' && l.format !== 'form')
  const form = letters.data?.letters.find((l) => l.status === 'approved' && l.format === 'form')
  const verified = (answers.data ?? []).filter((a) => a.verification_state === 'passed')
  const left = (answers.data?.length ?? 0) - verified.length
  if (!letter && !form && !(answers.data?.length ?? 0)) return null
  return (
    <>
      {letter && (
        <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); void copy(letter.text, 'Cover letter') }}>
          <Copy />
          Copy letter
        </Button>
      )}
      {form && (
        <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); void copy(form.text, 'Form text') }}>
          <Copy />
          Copy form text
        </Button>
      )}
      {(answers.data?.length ?? 0) > 0 && (
        <Button
          size="sm"
          variant="ghost"
          onClick={(e) => {
            e.stopPropagation()
            if (!verified.length) return void toast.error('Verify the answers in the job page first: unverified answers are never copied')
            void copy(verified.map((a) => `${a.question}\n${a.answer}`).join('\n\n'), `${verified.length} answer${verified.length === 1 ? '' : 's'}`)
            if (left > 0) toast.warning(`${left} answer${left === 1 ? ' is' : 's are'} not verified and was left out`)
          }}
        >
          <Copy />
          Copy answers
        </Button>
      )}
    </>
  )
}

export function ReadyTab() {
  const { data, isPending, error, refetch } = useReadyToApply()
  const [selected, setSelected] = useState<number | null>(null)
  const [applying, setApplying] = useState<ReadyItem | null>(null)
  const items = data ?? []
  const settings = useSettings()
  const chain = (settings.data?.values.tracking as { open_next_listing?: boolean } | undefined)?.open_next_listing !== false
  const next = useRef<ReadyItem | null>(null) // the job after the one being marked applied
  const byId = (id: number) => items.find((r) => r.application_id === id)

  useListKeyboard({
    ids: items.map((r) => r.application_id),
    selectedId: selected,
    onSelect: setSelected,
    actions: {
      o: (id) => {
        const r = byId(id)
        if (r) openListingAndCv(r.url, pdfUrl(r), letterUrl(r), { kind: 'app', id: r.application_id })
      },
      a: (id) => setApplying(byId(id) ?? null),
    },
    enabled: !applying,
  })

  if (isPending) return <SkeletonRows rows={5} />
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />
  if (items.length === 0)
    return (
      <EmptyState
        icon={Globe}
        title="Nothing ready to apply"
        description="Jobs land here when their CV is approved and there's no contact to email. Approve a CV in CV Studio to start."
        action={
          <div className="flex gap-2">
            <Button asChild size="sm" variant="default">
              <Link to="/pipeline">Open Pipeline</Link>
            </Button>
            <TourButton tour="applications" />
          </div>
        }
      />
    )

  return (
    <div className="min-h-0 flex-1 overflow-y-auto" data-tour="applications-ready">
      <p className="border-b border-border bg-bg-subtle px-6 py-2 text-xs text-fg-subtle">
        <strong className="font-medium text-fg-muted">{items.length} left</strong> · <Kbd>O</Kbd> open listing + download CV (and cover letter) · <Kbd>A</Kbd> mark applied, <Kbd>Enter</Kbd> confirms{chain ? ' and opens the next listing' : ''} · <Kbd>J</Kbd> <Kbd>K</Kbd> move
      </p>
      <div role="listbox" aria-label="Ready to apply">
        {items.map((r) => (
          <div
            key={r.application_id}
            data-row-id={r.application_id}
            role="option"
            aria-selected={selected === r.application_id}
            onClick={() => setSelected(r.application_id)}
            className={cn(
              'relative flex cursor-default items-center gap-3 border-b border-border px-6 py-3 transition-colors duration-120',
              selected === r.application_id ? 'bg-surface-selected' : 'hover:bg-surface-hover',
            )}
          >
            {selected === r.application_id && <span className="absolute inset-y-0 left-0 w-0.5 bg-primary" />}
            <div className="min-w-0 flex-1">
              <Link to={`/jobs/${r.job_id}`} className="truncate text-sm font-medium hover:underline">
                {r.title}
              </Link>
              <p className="truncate text-xs text-fg-muted">
                {r.company} · {r.track ?? 'No track'} · {r.country ? countryName(r.country) : 'Remote'} · approved CV v{r.cv_version}
                {r.letter_status === 'approved' && ` · cover letter v${r.letter_version}`}
              </p>
            </div>
            {r.letter_status !== 'approved' && (
              <Button size="sm" variant="ghost" asChild data-tour="applications-letter">
                <Link to={`/jobs/${r.job_id}/letter`}>
                  <FileText />
                  {r.letter_status === 'draft' ? `Review cover letter v${r.letter_version}` : 'Write cover letter'}
                </Link>
              </Button>
            )}
            {selected === r.application_id && <CopyButtons appId={r.application_id} />}
            <Button
              size="sm"
              variant={(selected ?? items[0].application_id) === r.application_id ? 'default' : 'secondary'}
              data-tour="applications-open" onClick={() => openListingAndCv(r.url, pdfUrl(r), letterUrl(r), { kind: 'app', id: r.application_id })}>
              {r.letter_status === 'approved' ? 'Open listing + CV + cover letter' : 'Open listing + CV'}
              <ArrowUpRight />
            </Button>
            <Button size="sm" data-tour="applications-mark" onClick={() => setApplying(r)}>
              <CircleCheck />
              Mark applied
            </Button>
          </div>
        ))}
      </div>
      <MarkAppliedDialog
        key={applying?.application_id ?? 'none'}
        target={applying ? { appId: applying.application_id, title: applying.title, company: applying.company } : null}
        cvVersion={applying?.cv_version ?? null}
        cvVersionId={applying?.cv_version_id}
        onOpenChange={(o) => !o && setApplying(null)}
        onConfirm={() => {
          // The next job: selected after this one is done, its listing opened right now (inside
          // the confirm key press or click: a browser only allows a new tab from a gesture).
          const i = items.findIndex((r) => r.application_id === applying?.application_id)
          next.current = items[i + 1] ?? items[i - 1] ?? null
          const n = next.current
          if (chain && n) openListingAndCv(n.url, pdfUrl(n), letterUrl(n), { kind: 'app', id: n.application_id })
        }}
        onDone={() => {
          if (next.current) setSelected(next.current.application_id)
          next.current = null
        }}
      />
    </div>
  )
}
