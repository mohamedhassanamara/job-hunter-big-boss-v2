import { useCallback, useEffect, useRef, useState } from 'react'

/** A countdown measured against the clock (not tick counts), so a throttled background tab
 * never drifts. `left` is in seconds; `onEnd` fires once when it reaches 0. */
export function useCountdown(onEnd?: () => void) {
  const [total, setTotal] = useState(0)
  const [left, setLeft] = useState(0)
  const [running, setRunning] = useState(false)
  const deadline = useRef(0)
  const endRef = useRef(onEnd)
  useEffect(() => {
    endRef.current = onEnd
  })

  useEffect(() => {
    if (!running) return
    const id = window.setInterval(() => {
      const rest = (deadline.current - Date.now()) / 1000
      if (rest <= 0) {
        setLeft(0)
        setRunning(false)
        endRef.current?.()
      } else setLeft(rest)
    }, 250)
    return () => window.clearInterval(id)
  }, [running])

  const start = useCallback((seconds: number) => {
    setTotal(seconds)
    setLeft(seconds)
    deadline.current = Date.now() + seconds * 1000
    setRunning(true)
  }, [])
  const pause = useCallback(() => setRunning(false), [])
  const resume = useCallback(() => {
    setLeft((rest) => {
      deadline.current = Date.now() + rest * 1000
      return rest
    })
    setRunning(true)
  }, [])
  const stop = useCallback(() => {
    setRunning(false)
    setLeft(0)
    setTotal(0)
  }, [])

  return { total, left, running, started: total > 0, start, pause, resume, stop }
}
