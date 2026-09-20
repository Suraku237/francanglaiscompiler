import { useCallback, useEffect, useRef, useState } from 'react'

export function useDownload() {
  const [error, setError] = useState('')
  const pending = useRef(new Map<string, number>())
  useEffect(() => () => {
    for (const [url, timer] of pending.current) {
      window.clearTimeout(timer)
      URL.revokeObjectURL(url)
    }
    pending.current.clear()
  }, [])
  const download = useCallback((blob: Blob, filename: string) => {
    setError('')
    let url: string | undefined
    const link = document.createElement('a')
    try {
      url = URL.createObjectURL(blob)
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      const savedUrl = url
      const timer = window.setTimeout(() => {
        URL.revokeObjectURL(savedUrl)
        pending.current.delete(savedUrl)
      }, 1000)
      pending.current.set(url, timer)
      return true
    } catch {
      if (url) URL.revokeObjectURL(url)
      setError('The download could not start. Check your browser download settings and try again.')
      return false
    } finally {
      link.remove()
    }
  }, [])
  return { download, error }
}
