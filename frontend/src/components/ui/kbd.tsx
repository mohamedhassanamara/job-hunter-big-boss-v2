import { cn } from '@/lib/utils'

export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        'inline-flex h-4.5 min-w-4.5 items-center justify-center rounded-sm border border-border bg-bg-subtle px-1 font-sans text-2xs font-medium text-fg-muted',
        className,
      )}
    >
      {children}
    </kbd>
  )
}
