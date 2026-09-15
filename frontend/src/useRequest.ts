import { useCallback, useEffect, useRef, useState } from 'react'
import { isCancelled, messageOf } from './api'

export function useRequest() {
  const controller = useRef<AbortController | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  const cancel = useCallback(() => {
    controller.current?.abort()
    controller.current = null
    setPending(false)
  }, [])

  const clearError = useCallback(() => setError(''), [])

  useEffect(() => () => {
    controller.current?.abort()
    controller.current = null
  }, [])

  const run = useCallback(async <T,>(
    work: (signal: AbortSignal) => Promise<T>,
    onSuccess: (result: T) => void,
  ) => {
    if (controller.current) return
    const current = new AbortController()
    controller.current = current
    setPending(true)
    setError('')
    try {
      const result = await work(current.signal)
      if (controller.current === current) onSuccess(result)
    } catch (cause: unknown) {
      if (controller.current === current && !isCancelled(cause)) setError(messageOf(cause))
    } finally {
      if (controller.current === current) {
        controller.current = null
        setPending(false)
      }
    }
  }, [])

  return { pending, error, run, cancel, clearError }
}
