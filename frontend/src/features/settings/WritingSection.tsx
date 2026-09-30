import { useState } from 'react'
import { toast } from 'sonner'
import { Select } from '@/components/ui/select'
import { useSaveSetting } from '@/lib/queries/library'
import type { SettingsView } from '@/lib/types'
import { Card, Field, SaveBar } from './sections'

interface WritingValue {
  work_authorization: 'never' | 'if_asked'
}

/** Rules shared by cover letters, form texts and cold emails. */
export function WritingSection({ settings }: { settings: SettingsView }) {
  const initial = (settings.values.writing as unknown as WritingValue) ?? { work_authorization: 'never' }
  const [value, setValue] = useState<WritingValue>(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  return (
    <Card
      title="Letters and emails"
      description="Applies to cover letters, form texts and cold emails. Checked in code: a draft breaking it is flagged and can't be approved."
      footer={
        <SaveBar
          dirty={dirty}
          saving={save.isPending}
          onReset={() => setValue(initial)}
          onSave={() =>
            save.mutate(
              { key: 'writing', value: value as unknown as Record<string, unknown> },
              { onSuccess: () => toast.success('Writing rules saved'), onError: (e) => toast.error(e.message) },
            )
          }
        />
      }
    >
      <div data-tour="settings-writing">
        <Field label="Mention work authorization" hint="Visa, sponsorship, right to work">
          <Select
            value={value.work_authorization}
            onValueChange={(v) => setValue({ work_authorization: v as WritingValue['work_authorization'] })}
            options={[
              { value: 'never', label: 'Never' },
              { value: 'if_asked', label: 'Only if the listing asks' },
            ]}
            className="w-64"
          />
        </Field>
      </div>
    </Card>
  )
}
