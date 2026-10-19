import { Check, LoaderCircle } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { ToneBadge } from '@/components/app/badges'
import { Button } from '@/components/ui/button'
import { useCompanyDomains, useSetEmailDomain } from '@/lib/queries/getContact'

/** Every domain known for the company (PDL's other companies with its name, the listing, the apply
 * link, the website's contact page, verified emails) and whether it receives email. Pick the one
 * providers should ask about. */
export function DomainPicker({ companyId }: { companyId: number }) {
  const { data, isPending, error } = useCompanyDomains(companyId, true)
  const set = useSetEmailDomain()
  const [all, setAll] = useState(false)
  if (isPending)
    return (
      <p className="flex items-center gap-2 text-xs text-fg-subtle">
        <LoaderCircle className="size-3.5 animate-spin" />
        Checking which domains receive email…
      </p>
    )
  if (error) return <p className="text-xs text-danger-fg">{error.message}</p>
  const pick = (emailDomain: string | null) => set.mutate({ companyId, emailDomain }, { onSuccess: () => toast.success(emailDomain ? `Providers will ask about ${emailDomain}` : 'Back to the website domain'), onError: (e) => toast.error(e.message) })
  const shown = all ? data.domains : data.domains.slice(0, 6)
  return (
    <div className="max-w-2xl space-y-1.5" data-tour="domain-picker">
      <p className="text-xs font-medium text-fg-subtle">Domains known for this company, best evidence first</p>
      <ul className="divide-y divide-border rounded-md border border-border bg-surface">
        {shown.map((d) => (
          <li key={d.domain} className="space-y-0.5 px-3 py-1.5">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">{d.domain}</span>
              <ToneBadge tone={d.mx === true ? 'green' : d.mx === false ? 'red' : 'gray'} dot={false}>
                {d.mx === true ? 'receives email' : d.mx === false ? 'no MX: no email' : 'unknown'}
              </ToneBadge>
              <span className="ml-auto shrink-0">
                {d.in_use ? (
                  <span className="flex items-center gap-1 text-xs text-success-fg">
                    <Check className="size-3.5" />
                    in use
                  </span>
                ) : (
                  <Button size="xs" variant="outline" disabled={set.isPending || d.mx === false} onClick={() => pick(d.is_website ? null : d.domain)}>
                    Use this one
                  </Button>
                )}
              </span>
            </div>
            <p className="truncate text-xs text-fg-subtle" title={d.note}>
              {d.is_website ? 'The website' : d.source}
              {d.note && !d.is_website ? `: ${d.note}` : ''}
            </p>
          </li>
        ))}
        {data.domains.length === 0 && <li className="px-3 py-2 text-xs text-fg-subtle">Nothing else is known yet: run Find contact once, or type the domain below.</li>}
      </ul>
      {data.domains.length > 6 && (
        <Button size="xs" variant="ghost" onClick={() => setAll((v) => !v)}>
          {all ? 'Show fewer' : `Show all ${data.domains.length}`}
        </Button>
      )}
      {data.email && data.email !== data.website && (
        <p className="text-xs text-fg-subtle">
          Email domain {data.email} is stored beside the website {data.website}; it is used for lookups.
        </p>
      )}
    </div>
  )
}
