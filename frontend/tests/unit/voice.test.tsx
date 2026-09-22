import { act, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { claimAudioFocus } from '../../src/audioFocus'
import { Dictionary } from '../../src/Dictionary'
import { ErrorNotice } from '../../src/components'
import { browserVoiceLanguage, useReadAloud } from '../../src/voice'
import { jsonResponse } from '../helpers'
import { lastSpoken, speechFixtures } from '../speechFixtures'

function SpokenDictionary({ active = true }: { active?: boolean }) {
  const speech = useReadAloud()
  return <><ErrorNotice message={speech.error} /><Dictionary active={active} onUseText={vi.fn()} speech={speech} /></>
}

describe('optional installed-voice read-aloud without recognition', () => {
  it.each([
    ['fr', 'fr'], ['en', 'en'], ['francanglais', 'fr'], ['pidgin', 'en'],
  ] as const)('maps %s to its approximate %s reference voice', (language, expected) => {
    expect(browserVoiceLanguage(language)).toBe(expected)
  })

  it.each(['fr', 'en'] as const)('reads with an installed local %s voice and releases finished output', (language) => {
    const { spoken, voices, recognition } = speechFixtures()
    const { result } = renderHook(useReadAloud)
    act(() => result.current.speak('result', 'Synthetic test text.', language))
    const utterance = lastSpoken(spoken)
    expect(utterance.lang).toBe(language === 'fr' ? 'fr-FR' : 'en-US')
    expect(utterance.voice).toBe(voices.find((voice) => voice.lang === utterance.lang))
    expect(utterance.rate).toBe(0.95)
    expect(result.current.activeId).toBe('result')
    act(() => utterance.onend?.())
    expect(result.current.activeId).toBeNull()
    expect(recognition).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('never silently uses a remote voice or the browser default if no local voice is available', () => {
    const { synthesis, voices, recognition } = speechFixtures()
    synthesis.getVoices.mockReturnValue(voices.map((voice) => ({ ...voice, localService: false })))
    const { result } = renderHook(useReadAloud)
    act(() => result.current.speak('source', 'Private source text', 'fr'))
    expect(result.current.error).toContain('Remote voices are not used')
    expect(result.current.activeId).toBeNull()
    expect(synthesis.speak).not.toHaveBeenCalled()
    expect(recognition).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('allows an explicit retry once local voices become available', () => {
    const { synthesis, voices } = speechFixtures()
    synthesis.getVoices.mockReturnValueOnce([])
    const { result } = renderHook(useReadAloud)
    act(() => result.current.speak('source', 'Test', 'en'))
    expect(result.current.error).toContain('Install a local')
    synthesis.getVoices.mockReturnValue(voices)
    act(() => result.current.speak('source', 'Test', 'en'))
    expect(result.current.error).toBe('')
    expect(synthesis.speak).toHaveBeenCalledOnce()
  })

  it('reports unsupported read-aloud without recording or a network fallback', () => {
    const { recognition } = speechFixtures()
    vi.stubGlobal('speechSynthesis', undefined)
    const { result } = renderHook(useReadAloud)
    expect(result.current.supported).toBe(false)
    act(() => result.current.speak('source', 'Test', 'en'))
    expect(result.current.error).toContain('not supported')
    expect(recognition).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('ignores stale output events and exposes current playback errors', () => {
    const { spoken } = speechFixtures()
    const { result } = renderHook(useReadAloud)
    act(() => result.current.speak('old', 'Previous text.', 'en'))
    const previous = lastSpoken(spoken)
    act(() => result.current.speak('new', 'Current text.', 'fr'))
    act(() => previous.onerror?.({ error: 'interrupted' }))
    expect(result.current.activeId).toBe('new')
    act(() => lastSpoken(spoken).onerror?.({ error: 'language-unavailable' }))
    expect(result.current.activeId).toBeNull()
    expect(result.current.error).toContain('local French or English voice')
  })

  it('stops read-aloud when raw recording or playback takes focus and on unmount', () => {
    const { synthesis } = speechFixtures()
    const { result, unmount } = renderHook(useReadAloud)
    act(() => result.current.speak('result', 'Synthetic text.', 'en'))
    const cancellations = synthesis.cancel.mock.calls.length
    act(() => claimAudioFocus({ microphone: true }))
    expect(synthesis.cancel).toHaveBeenCalledTimes(cancellations + 1)
    expect(result.current.activeId).toBeNull()
    act(() => result.current.speak('next', 'Synthetic text.', 'en'))
    unmount()
    expect(synthesis.cancel).toHaveBeenCalledTimes(cancellations + 3)
  })

  it('reads reference text only after a click, with no dictation or generated request surface', async () => {
    const { spoken, recognition } = speechFixtures()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({
      entries: [{ id: 'fixture', text: '  Tchop  ', aliases: ['Tchop'], language: 'francanglais', english_gloss: 'to eat',
        origin: 'Synthetic fixture', topic: 'Fixture', source_document: 'fixture.md', source_line: 2 }],
      total: 1, matched: 1, offset: 0, limit: 25, sources: ['fixture.md'],
    }))
    const user = userEvent.setup()
    render(<SpokenDictionary />)
    const read = await screen.findByRole('button', { name: 'Read aloud with a browser voice' })
    expect(spoken).toHaveLength(0)
    await user.click(read)
    expect(lastSpoken(spoken).text).toBe('  Tchop  ')
    expect(screen.getByRole('button', { name: 'Stop reading' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Stop reading' }))
    expect(screen.queryByRole('button', { name: /dictat|transcrib|Use your voice/i })).not.toBeInTheDocument()
    expect(recognition).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledOnce()
  })
})
