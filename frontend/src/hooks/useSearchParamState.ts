import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

/** Read/write URL search params so filters, tabs and selection survive reloads and links. */
export function useSearchParamState() {
  const [params, setParams] = useSearchParams()

  const get = useCallback((key: string) => params.get(key), [params])
  const getAll = useCallback((key: string) => params.getAll(key), [params])

  const set = useCallback(
    (updates: Record<string, string | string[] | number | null | undefined>, replace = true) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [key, value] of Object.entries(updates)) {
            next.delete(key)
            if (value === null || value === undefined || value === '') continue
            if (Array.isArray(value)) value.forEach((v) => next.append(key, v))
            else next.set(key, String(value))
          }
          return next
        },
        { replace },
      )
    },
    [setParams],
  )

  return { params, get, getAll, set }
}
