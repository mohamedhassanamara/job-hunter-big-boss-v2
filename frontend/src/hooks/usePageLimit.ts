import { useState } from 'react'

/** How many rows a list asks the server for: `page` at first, `page` more per call of `more`, and
 * back to one page when `key` (the filters) changes. */
export function usePageLimit(key: string, page: number) {
  const [state, setState] = useState({ key, limit: page })
  const limit = state.key === key ? state.limit : page
  return { limit, more: () => setState({ key, limit: limit + page }) }
}
