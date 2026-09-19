import { useEffect, useState } from 'react'
import { api } from './api'
import { useRequest } from './useRequest'

export const REFERENCE_PAGE_SIZE = 25

export function useReferenceSearch<T>(path: string, active: boolean) {
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<T | null>(null)
  const { pending, error, run, cancel, clearError } = useRequest()
  useEffect(() => {
    if (!active) return
    setResult(null)
    clearError()
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ query, offset: String(offset), limit: String(REFERENCE_PAGE_SIZE) })
      void run((signal) => api<T>(`${path}?${params}`, { signal }), setResult)
    }, 250)
    return () => {
      window.clearTimeout(timer)
      cancel()
    }
  }, [active, path, query, offset, revision, run, cancel, clearError])
  return {
    query, setQuery, offset, setOffset, result, pending, error,
    refresh: () => setRevision((value) => value + 1),
    loading: pending || (!result && !error),
  }
}
