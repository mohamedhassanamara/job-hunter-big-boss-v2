import { FlaskConical } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { useExperience, useRemoveTestData } from '@/lib/queries/library'

/**
 * Warns while the real workspace contains the test CV (experience items marked placeholder),
 * so test data can never be mistaken for the user's own.
 */
export function TestDataBanner({ showLink = false }: { showLink?: boolean }) {
  const { data } = useExperience()
  const remove = useRemoveTestData()
  const [confirming, setConfirming] = useState(false)
  const count = (data ?? []).filter((i) => i.is_placeholder).length
  if (!count) return null

  return (
    <>
      <div role="status" className="flex items-start gap-3 rounded-lg border border-tone-amber-border bg-warning-bg px-4 py-3">
        <FlaskConical className="mt-0.5 size-4 shrink-0 text-warning-fg" />
        <div className="min-w-0 flex-1 text-sm">
          <p className="font-medium text-warning-fg">Your experience contains test data</p>
          <p className="text-xs text-fg-muted">
            {count} items come from a test CV, so fit scores aren't about you yet. Edit an item to make it
            yours, or remove the test data and add your real experience.
          </p>
        </div>
        {showLink && (
          <Button size="sm" variant="ghost" asChild>
            <Link to="/experience">Open experience</Link>
          </Button>
        )}
        <Button size="sm" onClick={() => setConfirming(true)}>
          Remove test data
        </Button>
      </div>
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent title="Remove test data" className="max-w-md p-0">
          <div className="space-y-1 px-5 py-4">
            <h2 className="text-md font-semibold tracking-tight">Remove the test CV?</h2>
            <p className="text-sm text-fg-muted">
              Deletes the {count} test experience items and the test candidate profile. Items you have
              edited are yours and are kept. Existing fit scores will be marked stale.
            </p>
          </div>
          <div className="flex justify-end gap-2 border-t border-border px-5 py-3">
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(undefined, {
                  onSuccess: () => {
                    setConfirming(false)
                    toast.success('Test data removed')
                  },
                  onError: (e) => toast.error(e.message),
                })
              }
            >
              Remove test data
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
