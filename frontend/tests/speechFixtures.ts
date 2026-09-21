import { vi } from 'vitest'

export class FixtureRecognition {
  static instances: FixtureRecognition[] = []
  lang = ''
  continuous = false
  interimResults = false
  maxAlternatives = 1
  onresult: ((event: { resultIndex: number; results: { isFinal: boolean; length: number; 0: { transcript: string; confidence: number } }[] }) => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null
  onend: (() => void) | null = null
  start = vi.fn()
  stop = vi.fn(() => this.onend?.())
  abort = vi.fn()

  constructor() { FixtureRecognition.instances.push(this) }

  emit(text: string, isFinal = true) {
    this.onresult?.({
      resultIndex: 0,
      results: [{ isFinal, length: 1, 0: { transcript: text, confidence: 1 } }],
    })
  }
}

export class FixtureUtterance {
  lang = ''
  rate = 1
  voice: SpeechSynthesisVoice | null = null
  onend: (() => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null

  constructor(public text: string) {}
}

export function speechFixtures() {
  FixtureRecognition.instances = []
  const voices: SpeechSynthesisVoice[] = ['en-US', 'fr-FR'].map((lang) => ({
    lang, name: `Synthetic ${lang} voice`, voiceURI: `fixture:${lang}`, localService: true, default: lang === 'en-US',
  }))
  const spoken: FixtureUtterance[] = []
  const synthesis = {
    cancel: vi.fn(),
    getVoices: vi.fn(() => voices),
    speak: vi.fn((utterance: FixtureUtterance) => { spoken.push(utterance) }),
  }
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('SpeechRecognition', FixtureRecognition)
  vi.stubGlobal('webkitSpeechRecognition', undefined)
  vi.stubGlobal('SpeechSynthesisUtterance', FixtureUtterance)
  vi.stubGlobal('speechSynthesis', synthesis)
  return { synthesis, spoken, voices }
}

export function currentRecognition(): FixtureRecognition {
  const current = FixtureRecognition.instances.at(-1)
  if (!current) throw new Error('Expected a dictation session.')
  return current
}

export function lastSpoken(spoken: FixtureUtterance[]): FixtureUtterance {
  const current = spoken.at(-1)
  if (!current) throw new Error('Expected a read-aloud request.')
  return current
}
