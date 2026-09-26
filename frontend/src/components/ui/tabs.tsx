import { Tabs as TabsPrimitive } from 'radix-ui'
import * as React from 'react'
import { cn } from '@/lib/utils'

export const Tabs = TabsPrimitive.Root
export const TabsContent = TabsPrimitive.Content

/** Underline tabs, used in page headers. */
export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn('flex items-center gap-4', className)} {...props} />
}

export function TabsTrigger({
  className,
  children,
  count,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger> & { count?: number }) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        '-mb-px inline-flex h-9 items-center gap-1.5 border-b-2 border-transparent text-sm font-medium text-fg-muted transition-colors duration-120 hover:text-fg data-[state=active]:border-primary data-[state=active]:text-fg',
        className,
      )}
      {...props}
    >
      {children}
      {count !== undefined && (
        <span className="rounded-sm bg-surface-hover px-1.5 text-2xs font-medium text-fg-muted tabular-nums">
          {count}
        </span>
      )}
    </TabsPrimitive.Trigger>
  )
}

/** Segmented control look, for view toggles (board/table) and small filters. */
export function SegmentedList({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn('inline-flex h-8 items-center rounded-md border border-border bg-bg-subtle p-0.5', className)}
      {...props}
    />
  )
}

export function SegmentedTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        'inline-flex h-full items-center gap-1.5 whitespace-nowrap rounded-sm px-2.5 text-sm font-medium text-fg-muted transition-colors duration-120 hover:text-fg data-[state=active]:bg-surface data-[state=active]:text-fg data-[state=active]:shadow-sm [&_svg]:size-3.5',
        className,
      )}
      {...props}
    />
  )
}
