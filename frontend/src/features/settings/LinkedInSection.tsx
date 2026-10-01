import { useState } from 'react'
import { toast } from 'sonner'
import { BookmarkInstall } from '@/components/app/linkedin/BookmarkInstall'
import { Input } from '@/components/ui/input'
import { useSaveSetting } from '@/lib/queries/library'
import type { SettingsView } from '@/lib/types'
import { Card, Field, SaveBar } from './sections'

interface LinkedInValue {
  note_max_chars: number
  daily_requests: number
  followup_days: number
  gap_days: number
}

/** The LinkedIn bookmark (install) and the LinkedIn messages limits. */
export function LinkedInSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.linkedin as unknown as LinkedInValue
  const [value, setValue] = useState<LinkedInValue>(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  const num = (k: keyof LinkedInValue) => (e: React.ChangeEvent<HTMLInputElement>) => setValue({ ...value, [k]: Number(e.target.value) })
  return (
    <div className="space-y-6">
      <Card title="The LinkedIn bookmark" description="One click on a LinkedIn job page saves the job here and scores it. It reads only the page you're viewing, in your browser; the app never visits LinkedIn.">
        <div className="px-5 py-4">
          <BookmarkInstall />
        </div>
      </Card>
      <Card
        title="LinkedIn messages"
        description="Connection notes and follow-ups are drafted for you; you send them yourself on LinkedIn and mark them here."
        footer={
          <SaveBar
            dirty={dirty}
            saving={save.isPending}
            onReset={() => setValue(initial)}
            onSave={() =>
              save.mutate(
                { key: 'linkedin', value: value as unknown as Record<string, unknown> },
                { onSuccess: () => toast.success('LinkedIn settings saved'), onError: (e) => toast.error(e.message) },
              )
            }
          />
        }
      >
        <Field label="Connection note length" hint="Free accounts: 200 characters (and a few personalised notes a month). Premium: 300.">
          <div className="flex items-center gap-2 text-sm">
            <Input type="number" min={100} max={300} value={value.note_max_chars} onChange={num('note_max_chars')} className="w-24" aria-label="Connection note length" />
            characters
          </div>
        </Field>
        <Field label="Requests per day" hint="The counter warns at this number; it never blocks">
          <Input type="number" min={1} max={100} value={value.daily_requests} onChange={num('daily_requests')} className="w-24" aria-label="Requests per day" />
        </Field>
        <Field label="Follow-up reminder" hint="No answer after a request or a message">
          <div className="flex items-center gap-2 text-sm">
            <Input type="number" min={1} max={60} value={value.followup_days} onChange={num('followup_days')} className="w-24" aria-label="Follow-up reminder days" />
            days
          </div>
        </Field>
        <Field label="Email and LinkedIn gap" hint="Never suggested to the same person within this many days">
          <div className="flex items-center gap-2 text-sm">
            <Input type="number" min={0} max={30} value={value.gap_days} onChange={num('gap_days')} className="w-24" aria-label="Email and LinkedIn gap days" />
            days
          </div>
        </Field>
      </Card>
    </div>
  )
}
