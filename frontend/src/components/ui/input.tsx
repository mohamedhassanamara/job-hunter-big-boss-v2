import * as React from 'react'
import { cn } from '@/lib/utils'

export const inputClass =
  'w-full rounded-md border border-border-strong bg-surface px-2.5 text-sm text-fg placeholder:text-fg-subtle transition-colors duration-120 hover:border-fg-subtle focus-visible:border-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring disabled:opacity-50'

export function Input({ className, ...props }: React.ComponentProps<'input'>) {
  return <input className={cn(inputClass, 'h-8', className)} {...props} />
}

export function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return <textarea className={cn(inputClass, 'min-h-20 py-2 leading-6', className)} {...props} />
}
