import { useCallback, useEffect, useRef, useState } from 'react'
import type { Language, TranslationLanguage } from './types'

export function browserVoiceLanguage(language: TranslationLanguage): Language {
  return language === 'fr' || language === 'francanglais' ? 'fr' : 'en'
}

interface RecognitionAlternative {
  transcript: string
  confidence: number
}

interface RecognitionResult {
  readonly isFinal: boolean
  readonly length: number
  readonly [index: number]: RecognitionAlternative
}

interface RecognitionEvent extends Event {
  readonly resultIndex: number
  readonly results: {
    readonly length: number
    readonly [index: number]: RecognitionResult
  }
}

interface RecognitionErrorEvent extends Event {
  readonly error: string
  readonly message?: string
}

interface BrowserRecognition {
  lang: string
  continuous: boolean
  interimResults: boolean
  maxAlternatives: number
  onresult: ((event: RecognitionEvent) => void) | null
  onerror: ((event: RecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}

type RecognitionConstructor = new () => BrowserRecognition
type VoiceWindow = Window & {
  SpeechRecognition?: RecognitionConstructor
  webkitSpeechRecognition?: RecognitionConstructor
}

function recognitionConstructor(): RecognitionConstructor | undefined {
  const voiceWindow = window as VoiceWindow
  return voiceWindow.SpeechRecognition ?? voiceWindow.webkitSpeechRecognition
}

export function useDictation(language: Language, onTranscript: (text: string) => void) {
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [error, setError] = useState('')
  const recognition = useRef<BrowserRecognition | null>(null)
  const transcriptCallback = useRef(onTranscript)
  useEffect(() => {
    transcriptCallback.current = onTranscript
  }, [onTranscript])

  const cancel = useCallback(() => {
    const current = recognition.current
    recognition.current = null
    if (current) {
      current.onresult = null
      current.onerror = null
      current.onend = null
      current.abort()
    }
    setListening(false)
    setInterim('')
  }, [])

  useEffect(() => {
    cancel()
    setError('')
    return cancel
  }, [language, cancel])

  const toggle = useCallback(() => {
    if (recognition.current) {
      try {
        recognition.current.stop()
      } catch {
        cancel()
        setError('Dictation stopped unexpectedly. Please review your text and try again if needed.')
      }
      return
    }
    const Recognition = recognitionConstructor()
    if (!Recognition) {
      setError('Voice input is not supported in this browser. You can still type your message.')
      return
    }
    if (!window.isSecureContext) {
      setError('Microphone access needs HTTPS or localhost. You can still type.')
      return
    }
    setError('')
    setInterim('')
    const current = new Recognition()
    recognition.current = current
    current.lang = language === 'fr' ? 'fr-FR' : 'en-US'
    current.continuous = false
    current.interimResults = true
    current.maxAlternatives = 1
    current.onresult = (event) => {
      if (recognition.current !== current) return
      let preview = ''
      let finalText = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]
        const text = result?.[0]?.transcript ?? ''
        if (result?.isFinal) finalText += `${text} `
        else preview += text
      }
      if (finalText.trim()) transcriptCallback.current(finalText.trim())
      setInterim(preview)
    }
    current.onerror = (event) => {
      if (recognition.current !== current) return
      const messages: Record<string, string> = {
        'not-allowed': 'Microphone access was denied. Allow microphone access in your browser’s site settings, or type instead.',
        'service-not-allowed': 'Your browser’s speech service is unavailable or blocked. You can type instead.',
        'audio-capture': 'No microphone was found. Check your microphone connection and browser settings.',
        network: 'The browser’s speech service could not connect. Check your internet connection, or type instead.',
        'no-speech': 'No speech was detected. Try again when you’re ready.',
        'language-not-supported': 'This browser does not support dictation in the selected language. Try the other language or type instead.',
      }
      if (event.error !== 'aborted') {
        setError(messages[event.error] ?? 'Dictation could not start. Try again, or type your message.')
      }
      recognition.current = null
      current.onresult = null
      current.onerror = null
      current.onend = null
      current.abort()
      setListening(false)
      setInterim('')
    }
    current.onend = () => {
      if (recognition.current !== current) return
      recognition.current = null
      setListening(false)
      setInterim('')
    }
    try {
      current.start()
      setListening(true)
    } catch {
      recognition.current = null
      setError('Dictation could not start. Check microphone permissions and try again.')
      setListening(false)
    }
  }, [language, cancel])

  return { supported: Boolean(recognitionConstructor()), listening, interim, error, toggle, cancel }
}

export type Dictation = ReturnType<typeof useDictation>

export function useReadAloud() {
  const supported = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window
  const [activeId, setActiveId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const utterance = useRef<SpeechSynthesisUtterance | null>(null)

  const stop = useCallback(() => {
    utterance.current = null
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
    setActiveId(null)
    setError('')
  }, [])

  useEffect(() => stop, [stop])

  const speak = useCallback((id: string, text: string, language: Language) => {
    stop()
    setError('')
    if (!supported) {
      setError('Read-aloud is not supported in this browser.')
      return
    }
    const current = new SpeechSynthesisUtterance(text)
    current.lang = language === 'fr' ? 'fr-FR' : 'en-US'
    current.rate = 0.95
    const voices = window.speechSynthesis.getVoices()
    const voice = voices.find((item) => item.lang === current.lang) ??
      voices.find((item) => item.lang.toLowerCase().startsWith(language))
    if (voice) current.voice = voice
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
        setError('Your browser could not read this text aloud. Check that a French or English voice is installed.')
      }
    }
    try {
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
