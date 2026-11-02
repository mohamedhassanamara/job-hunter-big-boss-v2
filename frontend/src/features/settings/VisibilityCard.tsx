import { toast } from 'sonner'
import { TourButton } from '@/components/app/tour/TourButton'
import { Switch } from '@/components/ui/switch'
import { useSaveSetting } from '@/lib/queries/library'
import type { SettingsView } from '@/lib/types'
import { Card, Field } from './sections'

interface OutputVisibility {
  show_phone: boolean
  show_location: boolean
}

/** What documents print. Display only: matching and scoring keep using the stored values. */
export function VisibilityCard({ settings }: { settings: SettingsView }) {
  const stored = settings.values.output_visibility as Partial<OutputVisibility> | undefined
  const value: OutputVisibility = { show_phone: stored?.show_phone !== false, show_location: stored?.show_location !== false }
  const save = useSaveSetting()
  const toggle = (patch: Partial<OutputVisibility>) =>
    save.mutate(
      { key: 'output_visibility', value: { ...value, ...patch } as unknown as Record<string, unknown> },
      {
        onSuccess: () => toast.success('Visibility saved', { description: 'New CVs, letters and emails use it. Existing drafts change when you use Refresh headers on the Review CVs page.' }),
        onError: (e) => toast.error(e.message),
      },
    )
  return (
    <Card
      title="Visibility on documents"
      description="Choose what your CV header, cover letters and email signature print. Both are shown unless you turn them off."
    >
      <div data-tour="settings-visibility" className="space-y-4">
        <Field label="Show phone number" hint="CV and letter header, email signature">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={value.show_phone} disabled={save.isPending} onCheckedChange={(v) => toggle({ show_phone: v })} aria-label="Show the phone number on documents" />
            {value.show_phone ? 'Printed where your phone is used' : 'Hidden on every document'}
          </label>
        </Field>
        <Field label="Show location" hint="CV and letter header, the place on French letters">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={value.show_location} disabled={save.isPending} onCheckedChange={(v) => toggle({ show_location: v })} aria-label="Show the location on documents" />
            {value.show_location ? 'Printed where your location is used' : 'Hidden on every document, letters never state it'}
          </label>
        </Field>
        <p className="flex flex-wrap items-center gap-2 text-xs text-fg-subtle">
          Only what is printed changes. Fit scoring, country matching and checks still use the values above.
          <TourButton tour="visibility" />
        </p>
      </div>
    </Card>
  )
}
