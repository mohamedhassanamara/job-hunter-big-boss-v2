import { Switch as SwitchPrimitive } from 'radix-ui'
import * as React from 'react'
import { cn } from '@/lib/utils'

export function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        'inline-flex h-4.5 w-8 shrink-0 items-center rounded-full border border-transparent bg-border-strong transition-colors duration-120 data-[state=checked]:bg-primary disabled:opacity-50',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="block size-3.5 translate-x-0.5 rounded-full bg-surface shadow-sm transition-transform duration-120 data-[state=checked]:translate-x-[15px]" />
    </SwitchPrimitive.Root>
  )
}
