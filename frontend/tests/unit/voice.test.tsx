import { act, render, renderHook, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { Assistant } from '../../src/Assistant'
import { ErrorNotice } from '../../src/components'
import { Translator } from '../../src/Translator'
import { claimAudioFocus } from '../../src/audioFocus'
import { MAX_TEXT } from '../../src/types'
import { browserVoiceLanguage, useDictation, useReadAloud } from '../../src/voice'
import { translation } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'
import { currentRecognition, FixtureRecognition, lastSpoken, speechFixtures } from '../speechFixtures'

const scrollDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo')
beforeAll(() => Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() }))
afterAll(() => {
  if (scrollDescriptor) Object.defineProperty(HTMLElement.prototype, 'scrollTo', scrollDescriptor)
  else Reflect.deleteProperty(HTMLElement.prototype, 'scrollTo')
})

function SpeechWorkspace({ assistant = false, active = true }: { assistant?: boolean; active?: boolean }) {
  const speech = useReadAloud()
  return <>
    <ErrorNotice message={speech.error} />
    {assistant ? <Assistant active={active} aiAvailable speech={speech} /> :
      <Translator active={active} aiAvailable speech={speech} onOpenAssistant={vi.fn()} onOpenCollection={vi.fn()} onOpenImports={vi.fn()} />}
  </>
}

function assistantEnvironment() {
  vi.stubGlobal('matchMedia', vi.fn((media: string): MediaQueryList => ({
    media, matches: true, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(() => true),
  })))
}

describe('shared dictation and read-aloud', () => {
  it.each([
    ['fr', 'fr'], ['en', 'en'], ['francanglais', 'fr'], ['pidgin', 'en'],
  ] as const)('maps %s to its documented %s browser voice', (language, expected) => {
    expect(browserVoiceLanguage(language)).toBe(expected)
  })

  it('shows interim words, emits final words only, and stops without submitting anything', () => {
    speechFixtures()
    const received = vi.fn()
    const { result } = renderHook(() => useDictation('fr', received))
    act(() => result.current.toggle())
    const recognition = currentRecognition()
    expect(recognition.lang).toBe('fr-FR')
    expect(recognition.continuous).toBe(false)
    expect(recognition.interimResults).toBe(true)
    act(() => recognition.emit('Bonjour provisoire', false))
    expect(result.current.interim).toBe('Bonjour provisoire')
    expect(received).not.toHaveBeenCalled()
    act(() => recognition.emit(' Bonjour client. '))
    expect(received).toHaveBeenCalledExactlyOnceWith('Bonjour client.')
    act(() => result.current.toggle())
    expect(recognition.stop).toHaveBeenCalledOnce()
    expect(result.current.listening).toBe(false)
    expect(result.current.interim).toBe('')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('cancels old recognition on language change, rejects stale results and uses the new language', () => {
    speechFixtures()
    const received = vi.fn()
    const { result, rerender } = renderHook(({ language }: { language: 'fr' | 'en' }) => useDictation(language, received), {
      initialProps: { language: 'fr' },
    })
    act(() => result.current.toggle())
    const previous = currentRecognition()
    const lateResult = previous.onresult
    rerender({ language: 'en' })
    expect(previous.abort).toHaveBeenCalledOnce()
    act(() => lateResult?.({ resultIndex: 0, results: [{ isFinal: true, length: 1, 0: { transcript: 'Stale', confidence: 1 } }] }))
    expect(received).not.toHaveBeenCalled()
    act(() => result.current.toggle())
    expect(currentRecognition().lang).toBe('en-US')
  })

  it.each([
    ['not-allowed', 'Microphone access was denied'],
    ['service-not-allowed', 'speech service is unavailable'],
    ['audio-capture', 'No microphone was found'],
    ['network', 'speech service could not connect'],
    ['no-speech', 'No speech was detected'],
    ['language-not-supported', 'does not support dictation'],
  ])('surfaces %s and permits an explicit retry', (error, message) => {
    speechFixtures()
    const { result } = renderHook(() => useDictation('en', vi.fn()))
    act(() => result.current.toggle())
    const previous = currentRecognition()
    act(() => previous.onerror?.({ error }))
    expect(result.current.error).toContain(message)
    expect(result.current.listening).toBe(false)
    expect(previous.abort).toHaveBeenCalledOnce()
    act(() => result.current.toggle())
    expect(currentRecognition()).not.toBe(previous)
    expect(result.current.error).toBe('')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('reports unsupported dictation without trying to record', () => {
    speechFixtures()
    vi.stubGlobal('SpeechRecognition', undefined)
    const { result } = renderHook(() => useDictation('en', vi.fn()))
    expect(result.current.supported).toBe(false)
    act(() => result.current.toggle())
    expect(result.current.error).toContain('not supported')
    expect(FixtureRecognition.instances).toHaveLength(0)
  })

  it('does not start recognition on an insecure origin', () => {
    speechFixtures()
    vi.stubGlobal('isSecureContext', false)
    const { result } = renderHook(() => useDictation('en', vi.fn()))
    act(() => result.current.toggle())
    expect(result.current.error).toContain('HTTPS or localhost')
    expect(FixtureRecognition.instances).toHaveLength(0)
  })

  it('releases dictation when another audio activity takes focus and on unmount', () => {
    speechFixtures()
    const { result, unmount } = renderHook(() => useDictation('en', vi.fn()))
    act(() => result.current.toggle())
    const first = currentRecognition()
    act(() => claimAudioFocus({ anotherPlayer: true }))
    expect(first.abort).toHaveBeenCalledOnce()
    expect(result.current.listening).toBe(false)
    act(() => result.current.toggle())
    const second = currentRecognition()
    unmount()
    expect(second.abort).toHaveBeenCalledOnce()
  })

  it.each(['fr', 'en'] as const)('reads with the selected %s voice and releases the finished utterance', (language) => {
    const { spoken, voices } = speechFixtures()
    const { result } = renderHook(useReadAloud)
    act(() => result.current.speak('result', 'Synthetic test text.', language))
    const utterance = lastSpoken(spoken)
    expect(utterance.lang).toBe(language === 'fr' ? 'fr-FR' : 'en-US')
    expect(utterance.voice).toBe(voices.find((voice) => voice.lang === utterance.lang))
    expect(utterance.rate).toBe(0.95)
    expect(result.current.activeId).toBe('result')
    act(() => utterance.onend?.())
    expect(result.current.activeId).toBeNull()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('ignores stale speech events and exposes playback errors for the current utterance', () => {
    const { spoken } = speechFixtures()
    const { result } = renderHook(useReadAloud)
    act(() => result.current.speak('old', 'Previous text.', 'en'))
    const previous = lastSpoken(spoken)
    act(() => result.current.speak('new', 'Current text.', 'fr'))
    act(() => previous.onerror?.({ error: 'interrupted' }))
    expect(result.current.activeId).toBe('new')
    act(() => lastSpoken(spoken).onerror?.({ error: 'language-unavailable' }))
    expect(result.current.activeId).toBeNull()
    expect(result.current.error).toContain('French or English voice is installed')
  })

  it('stops read-aloud when recording or dictation takes focus', () => {
    const { synthesis } = speechFixtures()
    const { result } = renderHook(useReadAloud)
    act(() => result.current.speak('result', 'Synthetic text.', 'en'))
    const cancellations = synthesis.cancel.mock.calls.length
    act(() => claimAudioFocus({ microphone: true }))
    expect(synthesis.cancel).toHaveBeenCalledTimes(cancellations + 1)
    expect(result.current.activeId).toBeNull()
  })
})

describe('in-app spoken input and output wiring', () => {
  it('dictates source text, translates only on submission, and reads the actual target-language result', async () => {
    const { spoken } = speechFixtures()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(translation({
      translation: 'Hello customer.', source_language: 'fr', target_language: 'en',
    })))
    const user = userEvent.setup()
    render(<SpeechWorkspace />)
    await user.selectOptions(screen.getByLabelText('To'), 'en')
    await user.click(screen.getByRole('button', { name: 'Start French dictation' }))
    act(() => currentRecognition().emit('Bonjour client.', false))
    expect(screen.getByRole('textbox', { name: /text to translate/ })).toHaveValue('')
    expect(screen.getByRole('button', { name: 'Translate' })).toBeDisabled()
    act(() => currentRecognition().emit('Bonjour client.'))
    expect(screen.getByRole('textbox', { name: /text to translate/ })).toHaveValue('Bonjour client.')
    expect(fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Stop dictation' }))
    await user.click(screen.getByRole('button', { name: 'Translate' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toMatchObject({
      text: 'Bonjour client.', source_language: 'fr', target_language: 'en',
    })
    expect(await screen.findByText('Hello customer.')).toBeInTheDocument()
    expect(spoken).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Read aloud with a browser voice' }))
    expect(lastSpoken(spoken)).toMatchObject({ text: 'Hello customer.', lang: 'en-US' })
    await user.click(screen.getByRole('button', { name: 'Stop reading' }))
    expect(screen.getByRole('button', { name: 'Read aloud with a browser voice' })).toBeEnabled()
  })

  it('bounds dictated source text, makes truncation explicit and cancels the microphone on navigation', async () => {
    speechFixtures()
    const user = userEvent.setup()
    const view = render(<SpeechWorkspace />)
    await user.click(screen.getByRole('button', { name: 'Start French dictation' }))
    const recognition = currentRecognition()
    act(() => recognition.emit('A'.repeat(MAX_TEXT + 1)))
    expect(screen.getByRole('textbox', { name: /text to translate/ })).toHaveValue('A'.repeat(MAX_TEXT))
    expect(screen.getByText(/4,000-character limit was reached/)).toHaveAttribute('role', 'status')
    view.rerender(<SpeechWorkspace active={false} />)
    expect(recognition.abort).toHaveBeenCalledOnce()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('preserves typed text after a speech-service error and allows manual translation', async () => {
    speechFixtures()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(translation()))
    const user = userEvent.setup()
    render(<SpeechWorkspace />)
    await user.type(screen.getByRole('textbox', { name: /text to translate/ }), 'Typed fallback')
    await user.click(screen.getByRole('button', { name: 'Start French dictation' }))
    act(() => currentRecognition().onerror?.({ error: 'network' }))
    expect(screen.getByRole('alert')).toHaveTextContent('speech service could not connect')
    expect(screen.getByRole('textbox', { name: /text to translate/ })).toHaveValue('Typed fallback')
    expect(fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Translate' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toMatchObject({ text: 'Typed fallback' })
  })

  it('dictates an assistant message and reads replies only after explicit opt-in', async () => {
    assistantEnvironment()
    const { spoken } = speechFixtures()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ reply: 'Une proposition de test.', model: 'fixture-model', origin: 'ai', evidence: [] }))
    const user = userEvent.setup()
    render(<SpeechWorkspace assistant />)
    await user.selectOptions(screen.getByLabelText('From'), 'en')
    await user.click(screen.getByRole('button', { name: 'Start English dictation' }))
    act(() => currentRecognition().emit('Review this synthetic message.'))
    expect(screen.getByLabelText('Message for the assistant')).toHaveValue('Review this synthetic message.')
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    expect(fetch).not.toHaveBeenCalled()
    expect(screen.getByRole('checkbox', { name: 'Read replies aloud' })).not.toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Stop dictation' }))
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toMatchObject({
      message: 'Review this synthetic message.', language: 'fr', source_language: 'en', target_language: 'fr',
    })
    expect(await screen.findByText('Une proposition de test.')).toBeInTheDocument()
    expect(spoken).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Read aloud with a browser voice' }))
    expect(lastSpoken(spoken)).toMatchObject({ text: 'Une proposition de test.', lang: 'fr-FR' })
    await user.click(screen.getByRole('button', { name: 'Stop reading' }))
    await user.click(screen.getByRole('checkbox', { name: 'Read replies aloud' }))
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ reply: 'Seconde proposition.', model: 'fixture-model', origin: 'ai', evidence: [] }))
    await user.type(screen.getByLabelText('Message for the assistant'), 'A second synthetic message.')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Seconde proposition.')).toBeInTheDocument()
    expect(lastSpoken(spoken)).toMatchObject({ text: 'Seconde proposition.', lang: 'fr-FR' })
    await user.click(screen.getByRole('button', { name: 'Clear conversation' }))
    expect(screen.queryByRole('button', { name: 'Stop reading' })).not.toBeInTheDocument()
  })

  it('does not auto-read a late reply after the preference is turned off', async () => {
    assistantEnvironment()
    const { spoken } = speechFixtures()
    const pending = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(pending.promise)
    const user = userEvent.setup()
    render(<SpeechWorkspace assistant />)
    await user.click(screen.getByRole('checkbox', { name: 'Read replies aloud' }))
    await user.type(screen.getByLabelText('Message for the assistant'), 'A synthetic request.')
    await user.click(screen.getByRole('button', { name: 'Send' }))
    await user.click(screen.getByRole('checkbox', { name: 'Read replies aloud' }))
    await act(async () => pending.resolve(jsonResponse({ reply: 'Late synthetic reply.', model: 'fixture-model', origin: 'ai', evidence: [] })))
    expect(screen.getByText('Late synthetic reply.')).toBeInTheDocument()
    expect(spoken).toHaveLength(0)
  })
})
