import { CircleCheck, ExternalLink, Hourglass } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { BookmarkInstall } from '@/components/app/linkedin/BookmarkInstall'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tooltip } from '@/components/ui/tooltip'
import { countryName } from '@/lib/format'
import { linkedinSearchUrl } from '@/lib/linkedin'
import { useLinkedInCredits } from '@/lib/queries/linkedin'
import { useSaveSetting, useSearchProfile } from '@/lib/queries/library'
import type { SettingsView } from '@/lib/types'
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
  geo_ids: Record<string, { id: string; verified: boolean }>
}

/** The LinkedIn bookmark (install) and the LinkedIn messages limits. */
export function LinkedInSection({ settings }: { settings: SettingsView }) {
  const initial = settings.values.linkedin as unknown as LinkedInValue
  const [value, setValue] = useState<LinkedInValue>(initial)
  const save = useSaveSetting()
  const dirty = JSON.stringify(value) !== JSON.stringify(initial)
  const profile = useSearchProfile()
  const targets = profile.data?.locations ?? []
  const firstRole = profile.data?.tracks?.flatMap((t) => t.roles.map((r) => r.title)).find(Boolean) ?? ''
  const geo = (code: string) => value.geo_ids?.[code] ?? { id: '', verified: false }
  const setGeo = (code: string, patch: Partial<{ id: string; verified: boolean }>) =>
    setValue({ ...value, geo_ids: { ...value.geo_ids, [code]: { ...geo(code), ...patch } } })
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
        <Field label="Locations (geoId)" hint="LinkedIn's id for each target country. A text location can land in the wrong place (Jordan → Jordan, Pennsylvania), so links use these ids only; a country without one gets no link.">
          <div className="space-y-1.5" data-tour="linkedin-geo">
            {targets.length === 0 && <p className="text-sm text-fg-muted">Add target countries in Search profile first.</p>}
            {targets.map((code) => {
              const g = geo(code)
              return (
                <div key={code} className="flex min-w-0 items-center gap-1.5">
                  <span className="w-36 truncate text-sm" title={countryName(code)}>{countryName(code)}</span>
                  <Input
                    value={g.id}
                    onChange={(e) => setGeo(code, { id: e.target.value.replace(/\D/g, ''), verified: false })}
                    placeholder="geoId"
                    className="h-7 w-28 font-mono text-xs"
                    aria-label={`${countryName(code)} geoId`}
                  />
                  {!g.id ? (
                    <ToneBadge tone="red">No id: no links</ToneBadge>
                  ) : g.verified ? (
                    <ToneBadge tone="green">Confirmed</ToneBadge>
                  ) : (
                    <ToneBadge tone="amber">Unverified</ToneBadge>
                  )}
                  {g.id && (
                    <Button size="xs" variant="ghost" asChild>
                      <a href={linkedinSearchUrl(firstRole, g.id)} target="_blank" rel="noreferrer">
                        Test
                        <ExternalLink />
                      </a>
                    </Button>
                  )}
                  {g.id && !g.verified && (
                    <Tooltip content={`You opened Test link and LinkedIn showed ${countryName(code)}`}>
                      <Button size="xs" variant="ghost" onClick={() => setGeo(code, { verified: true })}>
                        <CircleCheck />
                        Confirm
                      </Button>
                    </Tooltip>
                  )}
                  {g.verified && (
                    <Button size="xs" variant="ghost" onClick={() => setGeo(code, { verified: false })}>
                      Mark unverified
                    </Button>
                  )}
                </div>
              )
            })}
            <p className="text-xs text-fg-subtle">Test opens a LinkedIn search for your first role there: check the location LinkedIn shows, confirm, then Save.</p>
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
