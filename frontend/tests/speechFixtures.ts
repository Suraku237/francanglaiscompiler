import { vi } from 'vitest'

export class FixtureUtterance {
  lang = ''
  rate = 1
  voice: SpeechSynthesisVoice | null = null
  onend: (() => void) | null = null
  onerror: ((event: { error: string }) => void) | null = null

  constructor(public text: string) {}
}

export function speechFixtures() {
  const voices: SpeechSynthesisVoice[] = ['en-US', 'fr-FR'].map((lang) => ({
    lang, name: `Synthetic ${lang} voice`, voiceURI: `fixture:${lang}`, localService: true, default: lang === 'en-US',
  }))
  const spoken: FixtureUtterance[] = []
  const recognition = vi.fn(() => { throw new Error('Speech recognition must never be started.') })
  const synthesis = {
    cancel: vi.fn(),
    getVoices: vi.fn(() => voices),
    speak: vi.fn((utterance: FixtureUtterance) => { spoken.push(utterance) }),
  }
  vi.stubGlobal('SpeechRecognition', recognition)
  vi.stubGlobal('webkitSpeechRecognition', recognition)
  vi.stubGlobal('SpeechSynthesisUtterance', FixtureUtterance)
  vi.stubGlobal('speechSynthesis', synthesis)
  return { synthesis, spoken, voices, recognition }
}

export function lastSpoken(spoken: FixtureUtterance[]): FixtureUtterance {
  const current = spoken.at(-1)
  if (!current) throw new Error('Expected a read-aloud request.')
  return current
}
