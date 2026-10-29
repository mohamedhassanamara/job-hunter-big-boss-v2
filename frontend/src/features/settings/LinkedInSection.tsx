import { Hourglass } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { BookmarkInstall } from '@/components/app/linkedin/BookmarkInstall'
import { Input } from '@/components/ui/input'
import { useLinkedInCredits } from '@/lib/queries/linkedin'
import { useSaveSetting } from '@/lib/queries/library'
import type { SettingsView } from '@/lib/types'
import { ExtensionCard } from './ExtensionCard'
import { Card, Field, SaveBar } from './sections'

interface LinkedInValue {
  note_max_chars: number
  daily_requests: number
  followup_days: number
  gap_days: number
  inmail_monthly_credits: number
  inmail_max_chars: number
  premium_end_date: string | null
  premium_remind_days: number
}

/** The LinkedIn bookmark (install) and the LinkedIn messages limits. */
export function LinkedInSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.linkedin as unknown as LinkedInValue
  const [value, setValue] = useState<LinkedInValue>(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  const num = (k: keyof LinkedInValue) => (e: React.ChangeEvent<HTMLInputElement>) => setValue({ ...value, [k]: Number(e.target.value) })
  const credits = useLinkedInCredits()
  const premium = credits.data?.premium
  const c = credits.data?.credits
  return (
    <div className="space-y-6">
      {premium && (
        <div
          className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${premium.remind ? 'border-tone-amber-border bg-warning-bg text-warning-fg' : 'border-border bg-surface text-fg-muted'}`}
          data-tour="linkedin-premium"
          role={premium.remind ? 'alert' : undefined}
        >
          <Hourglass className="mt-0.5 size-4 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className={premium.remind ? 'font-medium' : ''}>{premium.message}</p>
            {c && (
              <p className="mt-0.5 text-xs">
                This month: {c.used} InMail{c.used === 1 ? '' : 's'} sent, {c.refunded} credit{c.refunded === 1 ? '' : 's'} refunded by replies, {c.left} of {c.allowance} left (renews {c.renews_on}).
              </p>
            )}
          </div>
        </div>
      )}
      <ExtensionCard />
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
        <Field label="InMail credits per month" hint="Your Premium allowance (Career 5, Business 15, Sales Navigator 50). Sending an InMail uses one; a reply within 90 days gives it back.">
          <Input type="number" min={0} max={200} value={value.inmail_monthly_credits} onChange={num('inmail_monthly_credits')} className="w-24" aria-label="InMail credits per month" />
        </Field>
        <Field label="InMail length" hint="The longest InMail body the drafts and checks allow. Keep it short: a long one is rarely read.">
          <div className="flex items-center gap-2 text-sm">
            <Input type="number" min={300} max={1900} value={value.inmail_max_chars} onChange={num('inmail_max_chars')} className="w-24" aria-label="InMail length" />
            characters
          </div>
        </Field>
        <Field label="Premium ends on" hint="You get a reminder here before it ends, with what you got out of it, so you can decide in time whether to keep it.">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Input type="date" value={value.premium_end_date ?? ''} onChange={(e) => setValue({ ...value, premium_end_date: e.target.value || null })} className="w-44" aria-label="Premium end date" />
            <span className="text-fg-muted">remind me</span>
            <Input type="number" min={0} max={120} value={value.premium_remind_days} onChange={num('premium_remind_days')} className="w-20" aria-label="Remind days before" />
            <span className="text-fg-muted">days before</span>
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
