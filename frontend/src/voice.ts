import { useCallback, useEffect, useRef, useState } from 'react'
import { AUDIO_FOCUS_EVENT, claimAudioFocus, hasAudioFocus } from './audioFocus'
import type { Language, TranslationLanguage } from './types'

export function browserVoiceLanguage(language: TranslationLanguage): Language {
  return language === 'fr' || language === 'francanglais' ? 'fr' : 'en'
}

export function useReadAloud() {
  const supported = Boolean(window.speechSynthesis && window.SpeechSynthesisUtterance)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const utterance = useRef<SpeechSynthesisUtterance | null>(null)

  const stop = useCallback(() => {
    utterance.current = null
    window.speechSynthesis?.cancel()
    setActiveId(null)
    setError('')
  }, [])

  useEffect(() => stop, [stop])

  useEffect(() => {
    const onFocus = (event: Event) => { if (!hasAudioFocus(event, utterance.current)) stop() }
    window.addEventListener(AUDIO_FOCUS_EVENT, onFocus)
    return () => window.removeEventListener(AUDIO_FOCUS_EVENT, onFocus)
  }, [stop])

  const speak = useCallback((id: string, text: string, language: Language) => {
    stop()
    if (!supported) {
      setError('Read-aloud is not supported in this browser.')
      return
    }
    const current = new SpeechSynthesisUtterance(text)
    current.lang = language === 'fr' ? 'fr-FR' : 'en-US'
    current.rate = 0.95
    const voices = window.speechSynthesis.getVoices().filter((voice) => voice.localService)
    const voice = voices.find((item) => item.lang === current.lang) ??
      voices.find((item) => item.lang.toLowerCase().startsWith(language))
    if (!voice) {
      setError('Install a local French or English browser voice for read-aloud, then retry. Remote voices are not used.')
      return
    }
    current.voice = voice
    utterance.current = current
    current.onend = () => {
      if (utterance.current === current) {
        utterance.current = null
        setActiveId(null)
      }
    }
    current.onerror = (event) => {
      if (utterance.current !== current) return
      utterance.current = null
      setActiveId(null)
      if (event.error !== 'canceled' && event.error !== 'interrupted') {
        setError('Your browser could not read this text aloud. Check that a local French or English voice is installed.')
      }
    }
    try {
      claimAudioFocus(current)
      setActiveId(id)
      window.speechSynthesis.speak(current)
    } catch {
      utterance.current = null
      setActiveId(null)
      setError('Read-aloud could not start. Please try again.')
    }
  }, [stop, supported])

  return { supported, activeId, error, speak, stop }
}

export type ReadAloud = ReturnType<typeof useReadAloud>
