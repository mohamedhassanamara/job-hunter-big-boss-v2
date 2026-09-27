import { Command } from 'cmdk'
import { Check, Plus, X } from 'lucide-react'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { countryName } from '@/lib/format'
import { useCountries } from '@/lib/queries/library'

const REGION_ORDER = ['Europe', 'Middle East & North Africa', 'Other']
const itemClass =
  'flex h-8 cursor-default items-center gap-2 rounded-md px-2 text-sm text-fg select-none data-[selected=true]:bg-surface-hover'
const groupClass =
  '[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-2xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-fg-subtle'

/** Target countries: chips grouped by region, plus a searchable list of every country the
 * backend's location parser recognises (GET /api/countries). No list is hardcoded here. */
export function CountryPicker({ selected, onChange }: { selected: string[]; onChange: (codes: string[]) => void }) {
  const countries = useCountries()
  const [open, setOpen] = useState(false)
  const all = countries.data ?? []
  const regionOf = (code: string) => all.find((c) => c.code === code)?.region ?? 'Other'
  const toggle = (code: string) =>
    onChange(selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code])
  const groups = REGION_ORDER.map((region) => ({
    region,
    codes: selected.filter((c) => regionOf(c) === region),
  })).filter((g) => g.codes.length)

  return (
    <div className="flex flex-col gap-2">
      {groups.map((g) => (
        <div key={g.region} className="flex flex-col gap-1">
          <span className="text-2xs font-medium text-fg-subtle">{g.region}</span>
          <div className="flex flex-wrap gap-1.5">
            {g.codes.map((code) => (
              <span
                key={code}
                className="inline-flex h-7 items-center gap-1.5 rounded-md border border-primary bg-primary-subtle pr-1 pl-2.5 text-sm text-fg"
              >
                {countryName(code)}
                <button
                  type="button"
                  onClick={() => toggle(code)}
                  className="rounded-sm p-0.5 text-fg-subtle hover:text-fg"
                  aria-label={`Remove ${countryName(code)}`}
                >
                  <X className="size-3.5" />
                </button>
              </span>
            ))}
          </div>
        </div>
      ))}
      {!selected.length && <p className="text-sm text-fg-muted">No countries: only remote jobs will be kept.</p>}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="self-start" disabled={countries.isLoading}>
            <Plus /> Add country
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0">
          <Command loop>
            <Command.Input
              placeholder="Search countries…"
              className="h-9 w-full border-b border-border bg-transparent px-3 text-sm text-fg outline-none placeholder:text-fg-subtle"
            />
            <Command.List className="max-h-72 overflow-y-auto p-1">
              <Command.Empty className="px-3 py-6 text-center text-sm text-fg-muted">No country found</Command.Empty>
              {REGION_ORDER.map((region) => (
                <Command.Group key={region} heading={region} className={groupClass}>
                  {all
                    .filter((c) => c.region === region)
                    .sort((a, b) => countryName(a.code).localeCompare(countryName(b.code)))
                    .map((c) => (
                      <Command.Item
                        key={c.code}
                        value={`${countryName(c.code)} ${c.code}`}
                        onSelect={() => toggle(c.code)}
                        className={itemClass}
                      >
                        <Check className={selected.includes(c.code) ? 'size-4 text-primary' : 'size-4 opacity-0'} />
                        {countryName(c.code)}
                      </Command.Item>
                    ))}
                </Command.Group>
              ))}
            </Command.List>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  )
}
