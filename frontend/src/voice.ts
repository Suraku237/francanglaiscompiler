import { useCallback, useState } from 'react'
import { MAX_TEXT } from './types'
import type { Language, Ownership } from './types'

export interface ReadingSelection { id: string; text: string; language: Language }
export interface RecordedReading {
  id: string
  text: string
  language: Language
  audio_filename: string
  audio_url: string
  created_at: string
  updated_at: string
  ownership: Ownership
}

export function useReadAloud() {
  const supported = typeof window.HTMLAudioElement !== 'undefined'
  const [selection, setSelection] = useState<ReadingSelection | null>(null)
  const [error, setError] = useState('')

  const stop = useCallback(() => {
    setSelection(null)
    setError('')
  }, [])

  const speak = useCallback((id: string, text: string, language: Language) => {
    stop()
    if (!supported) {
      setError('Audio playback is not supported in this browser.')
      return
    }
    if (!text.trim() || text.length > MAX_TEXT) {
      setError('A recorded reading needs non-empty text of at most 4,000 characters.')
      return
    }
    setSelection({ id, text, language })
  }, [stop, supported])

  return { supported, activeId: selection?.id ?? null, selection, error, speak, stop }
}

export type ReadAloud = ReturnType<typeof useReadAloud>
