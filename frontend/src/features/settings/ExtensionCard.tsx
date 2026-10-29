import { Copy, KeyRound } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ErrorState, SkeletonRows } from '@/components/app/states'
import { TourButton } from '@/components/app/tour/TourButton'
import { Button } from '@/components/ui/button'
import { relativeTime } from '@/lib/format'
import { useCreateExtensionToken, useExtensionStatus, useRevokeExtensionToken } from '@/lib/queries/linkedin'
import { Card } from './sections'

/** The capture extension's token: created here, shown once, pasted into the extension's options. */
export function ExtensionCard() {
  const status = useExtensionStatus()
  const create = useCreateExtensionToken()
  const revoke = useRevokeExtensionToken()
  const [shown, setShown] = useState<string | null>(null)
  const s = status.data

  const make = () =>
    create.mutate(undefined, {
      onSuccess: (r) => setShown(r.token),
      onError: (e) => toast.error(e.message),
    })

  return (
    <Card
      title="Browser extension"
      description="The extension saves the job or person on the LinkedIn page you are viewing, and talks only to this app on your computer. It needs a token you create here; the app stores only a hash of it."
    >
      <div data-tour="ext-token" className="space-y-3">
        {status.isLoading ? (
          <SkeletonRows rows={2} />
        ) : status.isError || !s ? (
          <ErrorState error={status.error ?? new Error('Could not load the extension status')} onRetry={() => status.refetch()} compact />
        ) : !s.available ? (
          <p className="text-sm text-fg-muted">The extension works on your real workspace, not in the tour sandbox.</p>
        ) : (
          <>
            {shown ? (
              <div className="space-y-2 rounded-md border border-border bg-surface-raised p-3">
                <p className="text-sm font-medium">Copy your token now: it is shown only once.</p>
                <div className="flex items-center gap-2">
                  <code className="min-w-0 flex-1 truncate rounded bg-surface px-2 py-1 font-mono text-xs">{shown}</code>
                  <Button
                    size="sm"
                    onClick={() => navigator.clipboard.writeText(shown).then(() => toast.success('Token copied'), () => toast.error('Could not copy: select the text and copy it'))}
                  >
                    <Copy />
                    Copy
                  </Button>
                </div>
                <p className="text-xs text-fg-muted">Paste it into the extension's options. Creating a new token stops the old one working.</p>
                <Button size="sm" variant="ghost" onClick={() => setShown(null)}>
                  I copied it
                </Button>
              </div>
            ) : s.exists ? (
              <p className="text-sm text-fg-muted">
                A token is active (created {relativeTime(s.created_at)}
                {s.last_used_at ? `, last used ${relativeTime(s.last_used_at)}` : ', not used yet'}). It opens only the extension's routes.
              </p>
            ) : (
              <p className="text-sm text-fg-muted">No token yet, so the extension cannot save anything. Create one, then paste it into the extension's options.</p>
            )}
            <div className="flex flex-wrap items-center gap-2">
              {s.exists ? (
                <>
                  <Button size="sm" variant="secondary" onClick={make} disabled={create.isPending}>
                    <KeyRound />
                    Replace token
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={revoke.isPending}
                    onClick={() => revoke.mutate(undefined, { onSuccess: () => { setShown(null); toast.success('Token revoked') }, onError: (e) => toast.error(e.message) })}
                  >
                    Revoke
                  </Button>
                </>
              ) : (
                <Button size="sm" onClick={make} disabled={create.isPending}>
                  <KeyRound />
                  Create token
                </Button>
              )}
              <TourButton tour="linkedin-extension" />
            </div>
          </>
        )}
      </div>
    </Card>
  )
}
