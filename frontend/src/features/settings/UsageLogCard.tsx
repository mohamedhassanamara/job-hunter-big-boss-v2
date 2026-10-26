import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { useSaveSetting } from '@/lib/queries/library'
import { useClearUsage, useUsageReport } from '@/lib/queries/usage'
import { setUsageEnabled } from '@/lib/usage'
import type { SettingsView } from '@/lib/types'
import { Card, Field } from './sections'

const minutes = (m: number) => (m < 1 ? '<1 min' : `${Math.round(m)} min`)

/** Local usage log (services/usage.py): screens, key actions, slow waits, idle gaps. */
export function UsageLogCard({ settings }: { settings: SettingsView }) {
  const enabled = (settings.values.usage_log as { enabled?: boolean } | undefined)?.enabled ?? true
  const save = useSaveSetting()
  const clear = useClearUsage()
  const report = useUsageReport()
  const latest = report.data?.sessions.at(-1)
  const topScreens = latest?.per_screen.slice(0, 3) ?? []
  return (
    <Card
      title="Usage log"
      description="Measures where your time goes in a batch. Stored only in this database: route names, action names, job ids and durations. Never page content, drafts or CV text, and nothing leaves this machine."
    >
      <div data-tour="usage-log" className="space-y-4">
        <Field label="Record usage" hint="Route changes, shortlist / approve / generate / open listing / mark applied / queue add, time on each screen, slow requests and 5-minute idle gaps.">
          <Switch
            checked={enabled}
            aria-label="Record the usage log"
            onCheckedChange={(on) =>
              save.mutate(
                { key: 'usage_log', value: { enabled: on } },
                {
                  onSuccess: () => {
                    setUsageEnabled(on)
                    toast.success(on ? 'Usage log on' : 'Usage log off')
                  },
                  onError: (e) => toast.error(e.message),
                },
              )
            }
          />
        </Field>
        <Field label="Latest session" hint="Full report: make usage-report (ARGS=&quot;--last 3&quot; for more).">
          {!latest ? (
            <p className="pt-1.5 text-sm text-fg-muted">
              {enabled ? 'Nothing recorded yet. Work through a batch as usual, then come back here.' : 'The log is off.'}
            </p>
          ) : (
            <div className="space-y-1 pt-1.5 text-sm text-fg-muted">
              <p>
                {minutes(latest.wall_minutes)} long, {minutes(latest.active_minutes)} active, {latest.screen_visits} screen visits,{' '}
                {latest.screen_switches} route changes, {Math.round(latest.waits_total_s)} s waiting on slow requests,{' '}
                {latest.idle_gaps.length} idle gaps.
              </p>
              {topScreens.length > 0 && (
                <p>Most time: {topScreens.map((d) => `${d.screen} (${Math.round(d.active_s / 60)} min)`).join(', ')}.</p>
              )}
              {latest.longest_waits[0] && (
                <p>Longest wait: {Math.round(latest.longest_waits[0].seconds)} s, {latest.longest_waits[0].name}.</p>
              )}
            </div>
          )}
        </Field>
        <Field label="Clear usage log" hint="Deletes every recorded entry.">
          <Button size="sm" variant="ghost" className="text-danger-fg hover:text-danger-fg" disabled={clear.isPending} onClick={() => clear.mutate()}>
            Clear usage log
          </Button>
        </Field>
      </div>
    </Card>
  )
}
