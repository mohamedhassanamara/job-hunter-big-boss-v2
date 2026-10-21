import { useGenerationStatus } from '@/lib/queries/workflow'

/** Mounted once in the shell. Background drafting is silent (no toasts): this only keeps the cards
 * fresh, refreshing them when a CV or email draft is ready (or failed). */
export function GenerationWatcher() {
  useGenerationStatus()
  return null
}
