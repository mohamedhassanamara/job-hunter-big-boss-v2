import { useEffect, useRef } from 'react'

/** Keeps an editor's local text in step with the server copy when the server changes it (a
 * suggested fix was applied) and you have no unsaved edit: your own typing is never overwritten. */
export function useSyncFromServer<T>(server: T, local: T, setLocal: (value: T) => void) {
  const previous = useRef(server)
  const key = JSON.stringify(server)
  useEffect(() => {
    if (key === JSON.stringify(previous.current)) return
    if (JSON.stringify(local) === JSON.stringify(previous.current)) setLocal(server)
    previous.current = server
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a change of the server copy matters
  }, [key])
}
