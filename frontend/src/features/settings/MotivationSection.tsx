import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useSaveSetting } from '@/lib/queries/library'
import type { MotivationSettings, SettingsView } from '@/lib/types'
import { Card, Field, SaveBar } from './sections'

/** Streak, chests and the Motiv Center. Off hides all of it; nothing else changes. */
export function MotivationSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.motivation as unknown as MotivationSettings
  const [value, setValue] = useState<MotivationSettings>(initial)
  const save = useSaveSetting()
  const qc = useQueryClient()
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  const num = (k: keyof MotivationSettings) => (e: React.ChangeEvent<HTMLInputElement>) => setValue({ ...value, [k]: Number(e.target.value) })
  return (
    <Card
      title="Motivation"
      description="A workday streak, chests with tokens, a shop of your own rewards, and the Motiv Center. It only reads your job data and never changes or blocks a step."
      footer={
        <SaveBar
          dirty={dirty}
          saving={save.isPending}
          onReset={() => setValue(initial)}
          onSave={() =>
            save.mutate(
              { key: 'motivation', value: value as unknown as Record<string, unknown> },
              {
                onSuccess: () => (toast.success('Motivation settings saved'), void qc.invalidateQueries({ queryKey: ['motivation'] })),
                onError: (e) => toast.error(e.message),
              },
            )
          }
        />
      }
    >
      <Field label="Show motivation features" hint="Off hides the streak, tokens, Today cards and the Motiv Center">
        <Switch checked={value.enabled} onCheckedChange={(v) => setValue({ ...value, enabled: v })} aria-label="Show motivation features" />
      </Field>
      <Field label="Daily goal" hint="Applications per workday (Monday to Friday) to keep the streak">
        <Input type="number" min={1} max={50} value={value.daily_goal} onChange={num('daily_goal')} className="w-24" aria-label="Daily goal" />
      </Field>
      <Field label="What counts" hint="A job marked Applied always counts, on the day you mark it">
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2">
            <Switch checked={value.count_emails} onCheckedChange={(v) => setValue({ ...value, count_emails: v })} />
            Sent cold emails
          </label>
          <label className="flex items-center gap-2">
            <Switch checked={value.count_linkedin} onCheckedChange={(v) => setValue({ ...value, count_linkedin: v })} />
            Sent LinkedIn requests
          </label>
        </div>
      </Field>
      <Field label="Chest goal" hint={`Applications per chest (1 to 10 tokens each). Counting since ${value.chests_since ?? 'today'}.`}>
        <Input type="number" min={1} max={1000} value={value.chest_goal} onChange={num('chest_goal')} className="w-24" aria-label="Chest goal" />
      </Field>
      <Field label="Timezone" hint="When your day ends (midnight) for the streak">
        <Input value={value.timezone} onChange={(e) => setValue({ ...value, timezone: e.target.value })} className="w-56" aria-label="Timezone" />
      </Field>
      <Field label="Upload limit" hint="Per image or video in My goals">
        <div className="flex items-center gap-2 text-sm">
          <Input type="number" min={1} max={2000} value={value.max_upload_mb} onChange={num('max_upload_mb')} className="w-24" aria-label="Upload limit" />
          MB
        </div>
      </Field>
    </Card>
  )
}
