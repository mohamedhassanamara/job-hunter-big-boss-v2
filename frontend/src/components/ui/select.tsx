import { Select as SelectPrimitive } from 'radix-ui'
import { Check, ChevronDown } from 'lucide-react'
import * as React from 'react'
import { cn } from '@/lib/utils'

export interface SelectOption {
  value: string
  label: React.ReactNode
  disabled?: boolean
}

/** Compact single-select. Use for enumerations with ≤ ~12 options. */
export function Select({
  value,
  onValueChange,
  options,
  placeholder,
  className,
  size = 'md',
  'aria-label': ariaLabel,
}: {
  value: string | undefined
  onValueChange: (v: string) => void
  options: SelectOption[]
  placeholder?: string
  className?: string
  size?: 'sm' | 'md'
  'aria-label'?: string
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
      <SelectPrimitive.Trigger
        aria-label={ariaLabel}
        className={cn(
          'inline-flex items-center justify-between gap-2 rounded-md border border-border-strong bg-surface px-2.5 text-sm text-fg hover:border-fg-subtle focus-visible:border-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring data-[placeholder]:text-fg-subtle',
          size === 'sm' ? 'h-7' : 'h-8',
          className,
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown className="size-3.5 text-fg-subtle" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className="z-50 max-h-80 min-w-(--radix-select-trigger-width) overflow-hidden rounded-lg border border-border bg-surface-raised p-1 shadow-lg data-[state=open]:animate-in data-[state=open]:fade-in-0"
        >
          <SelectPrimitive.Viewport>
            {options.map((o) => (
              <SelectPrimitive.Item
                key={o.value}
                value={o.value}
                disabled={o.disabled}
                className="relative flex h-8 cursor-default items-center rounded-md pr-8 pl-2 text-sm outline-none select-none data-[disabled]:opacity-40 data-[highlighted]:bg-surface-hover"
              >
                <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator className="absolute right-2">
                  <Check className="size-4 text-primary" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}
