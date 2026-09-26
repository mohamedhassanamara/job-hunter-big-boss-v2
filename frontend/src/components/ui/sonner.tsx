import { Toaster as Sonner } from 'sonner'
import { useTheme } from '@/components/app/theme'

export function Toaster() {
  const { resolved } = useTheme()
  return (
    <Sonner
      theme={resolved}
      position="bottom-right"
      offset={16}
      gap={8}
      toastOptions={{
        classNames: {
          toast:
            'group !rounded-lg !border !border-border !bg-surface-raised !text-fg !shadow-lg !text-sm !gap-2 !py-3 !px-3.5',
          description: '!text-fg-muted !text-xs',
          actionButton:
            '!bg-transparent !text-primary !font-medium !text-sm hover:!bg-primary-subtle !h-7 !px-2 !rounded-md',
          cancelButton: '!bg-transparent !text-fg-muted',
          icon: '!size-4',
          success: '[&_[data-icon]]:!text-success-dot',
          error: '[&_[data-icon]]:!text-danger-dot',
        },
      }}
    />
  )
}
