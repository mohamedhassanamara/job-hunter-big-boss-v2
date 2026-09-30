import { useState } from 'react'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { useSaveSetting } from '@/lib/queries/library'
import type { SettingsView } from '@/lib/types'
import { Card, Field, SaveBar } from './sections'

interface ResearchValue {
  refresh_days: number
  max_pages: number
  max_selected: number
  news: { gdelt: boolean; google_news: boolean }
}

/** Company research for cold emails: runs only at the email draft step or with Research now. */
export function ResearchSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.research as unknown as ResearchValue
  const [value, setValue] = useState<ResearchValue>(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  return (
    <Card
      title="Company research"
      description="Before an email is drafted, the company's own site and recent news are read and a model extracts facts with their exact quotes (checked in code). Never on discovery, scoring or in bulk. Model: gemma4:31b-cloud, falling back to the local gemma4:12b (quota or errors)."
      footer={
        <SaveBar
          dirty={dirty}
          saving={save.isPending}
          onReset={() => setValue(initial)}
          onSave={() =>
            save.mutate(
              { key: 'research', value: value as unknown as Record<string, unknown> },
              { onSuccess: () => toast.success('Research settings saved'), onError: (e) => toast.error(e.message) },
            )
          }
        />
      }
    >
      <Field label="Reuse signals for" hint="Days before a company is researched again">
        <Input type="number" min={1} max={365} value={value.refresh_days} onChange={(e) => setValue({ ...value, refresh_days: Number(e.target.value) })} className="w-24" />
      </Field>
      <Field label="Pages per company" hint="From its own site (robots.txt respected)">
        <Input type="number" min={2} max={15} value={value.max_pages} onChange={(e) => setValue({ ...value, max_pages: Number(e.target.value) })} className="w-24" />
      </Field>
      <Field label="News: GDELT" hint="Free public news API, no key">
        <Switch checked={value.news.gdelt} onCheckedChange={(v) => setValue({ ...value, news: { ...value.news, gdelt: v } })} aria-label="GDELT news" />
      </Field>
      <Field label="News: Google News RSS" hint="Free feed, no key (unofficial: may change)">
        <Switch checked={value.news.google_news} onCheckedChange={(v) => setValue({ ...value, news: { ...value.news, google_news: v } })} aria-label="Google News RSS" />
      </Field>
    </Card>
  )
}
