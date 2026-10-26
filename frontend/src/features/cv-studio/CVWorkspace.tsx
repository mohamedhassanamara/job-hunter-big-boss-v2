import { LoaderCircle } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { ErrorState } from '@/components/app/states'
import { Tooltip } from '@/components/ui/tooltip'
import { apiUrl } from '@/lib/api'
import { keys } from '@/lib/queries/keys'
import { usePatchCV } from '@/lib/queries/workflow'
import type { CVPatchInput, CVStudio, CVVersion } from '@/lib/types'
import { CVContentPanel } from './CVContentPanel'

/** The page-count / fill pill and the two-pane workspace (editable content + PDF preview), shared
 * by CV Studio and Review CVs. */
export function FitBadge({ version }: { version: CVVersion }) {
  if (version.error) return <ToneBadge tone="red">LaTeX error</ToneBadge>
  if (version.page_count == null) return <ToneBadge tone="gray">Not compiled</ToneBadge>
  const pct = version.fill != null ? Math.round(version.fill * 100) : null
  const ok = version.page_count === 1
  return (
    <Tooltip content={`${version.fit_passes} fit pass${version.fit_passes === 1 ? '' : 'es'} · template ${version.template}${version.duration_ms ? ` · ${Math.round(version.duration_ms / 1000)}s` : ''}`}>
      <span>
        <ToneBadge tone={ok ? 'green' : 'red'}>
          {version.page_count} page{version.page_count === 1 ? '' : 's'}
          {pct != null && ok ? ` · ${pct}% full` : ''}
        </ToneBadge>
      </span>
    </Tooltip>
  )
}

export function Workspace({ studio, version }: { studio: CVStudio; version: CVVersion }) {
  const patch = usePatchCV()
  const qc = useQueryClient()
  const readOnly = version.status === 'superseded'
  const onPatch = (body: CVPatchInput) =>
    patch.mutate(
      { id: version.id, ...body },
      {
        onSuccess: (v) => {
          if (v.id !== version.id) toast.success(`Changes saved as a new draft (v${v.version})`)
        },
        onError: (e) => toast.error(e.message),
      },
    )
  return (
    <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] max-xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
      <div data-tour="cv-editor" className="min-h-0 overflow-y-auto border-r border-border bg-bg">
        <div className="sticky top-0 z-10 flex h-10 items-center justify-between border-b border-border bg-bg px-5 text-xs">
          <span className="font-medium text-fg-muted">From your experience pool</span>
          <span className="text-fg-subtle">
            {patch.isPending ? 'Re-fitting the page…' : readOnly ? 'Superseded, read only' : version.status === 'approved' ? 'Changes create a new draft' : 'Toggle or edit: the page re-fits'}
          </span>
        </div>
        {studio.usage ? (
          <CVContentPanel version={version} usage={studio.usage} readiness={studio.readiness} readOnly={readOnly} busy={patch.isPending} onPatch={onPatch} />
        ) : (
          <p className="px-5 py-4 text-sm text-fg-muted">This version has no generator plan. Regenerate to edit it.</p>
        )}
      </div>
      <div data-tour="cv-preview" className="relative min-h-0 bg-bg-subtle">
        {version.error ? (
          <div className="p-6">
            <ErrorState error={new Error(version.error.split('\n')[0])} />
            <pre className="mt-3 max-h-80 overflow-auto rounded-md bg-surface p-3 text-2xs text-fg-muted">{version.error}</pre>
          </div>
        ) : (
          <iframe
            key={`${version.id}-${version.updated_at}`}
            title="CV preview"
            // A version without a PDF (sample data) is compiled on first view: refresh its badge.
            onLoad={() => version.page_count == null && void qc.invalidateQueries({ queryKey: keys.cv(version.application_id) })}
            src={`${apiUrl(`/cv/${version.id}/pdf`, { v: version.updated_at })}#view=FitH&toolbar=0`}
            className="h-full w-full border-0"
          />
        )}
        {patch.isPending && (
          <div className="absolute inset-0 flex items-center justify-center bg-bg/60">
            <span className="inline-flex items-center gap-2 rounded-md bg-surface px-3 py-2 text-sm shadow-sm">
              <LoaderCircle className="size-4 animate-spin text-primary" />
              Recompiling…
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
