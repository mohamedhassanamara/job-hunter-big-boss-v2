import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import { ThemeProvider } from '@/components/app/ThemeProvider'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { ApiError } from '@/lib/api'
import { router } from '@/router'
import '@/styles/index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      // Local API: an unreachable backend (proxy 502/network) or a 4xx won't fix itself on retry,
      // so show the error state immediately. Anything else gets one retry.
      retry: (count, error) =>
        !(error instanceof ApiError && (error.status === 0 || error.status === 502 || error.status < 500)) &&
        count < 1,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <TooltipProvider delayDuration={400} skipDelayDuration={200}>
          <RouterProvider router={router} />
          <Toaster />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
)
