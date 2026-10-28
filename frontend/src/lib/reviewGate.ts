import { useSyncExternalStore } from 'react'
import type { DraftReview } from '@/lib/types'

/** What the reviewer last said about which exact text. A draft counts as reviewed (`hasCheckedClaims`)
 * only while its text still equals the reviewed text: a new draft has no entry and an edit stops matching. */
interface Entry {
  text: string
  review: DraftReview
}

const store = new Map<string, Entry>()
const listeners = new Set<() => void>()
let version = 0

const subscribe = (fn: () => void) => {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function markReviewed(key: string, text: string, review: DraftReview) {
  store.set(key, { text, review })
  version += 1
  listeners.forEach((fn) => fn())
}

/** The reviewed text's review for this key, and whether the current text is still that text. */
export function reviewFor(key: string, text: string): { review: DraftReview | null; reviewed: boolean } {
  const entry = store.get(key)
  return { review: entry?.review ?? null, reviewed: !!entry && entry.text === text }
}

/** Re-renders when any review is recorded. */
export function useReviewVersion() {
  return useSyncExternalStore(subscribe, () => version)
}

export const emailKey = (id: number) => `email:${id}`
export const linkedinKey = (id: number, kind: string) => `linkedin:${id}:${kind}`
export const emailText = (subject: string, body: string) => `${subject}\n\n${body}`
