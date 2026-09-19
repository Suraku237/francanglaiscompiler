import type { ComponentProps } from 'react'
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Translator } from '../../src/Translator'
import { MAX_TEXT } from '../../src/types'
import type { ReadAloud } from '../../src/voice'
import { translation } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'

function renderTranslator(overrides: Partial<ComponentProps<typeof Translator>> = {}) {
  const speech: ReadAloud = { supported: false, activeId: null, error: '', speak: vi.fn(), stop: vi.fn() }
  const props = {
    active: true,
    aiAvailable: true,
    speech,
    onOpenAssistant: vi.fn(),
    onOpenCollection: vi.fn(),
    onOpenImports: vi.fn(),
    ...overrides,
  }
  const view = render(<Translator {...props} />)
  return { ...view, props, user: userEvent.setup() }
}

const sourceText = () => screen.getByRole('textbox', { name: /text to translate/ })
const submit = () => screen.getByRole('button', { name: 'Translate' })

describe('translator trust and submission boundaries', () => {
  it('labels a dictionary answer as local reference material rather than approved fieldwork or AI', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(translation({
      translation: 'Reference meaning', origin: 'dictionary', model: 'local-dictionary',
      evidence: [{
        id: 'dictionary:fixture.md:4', text: 'fixture', language: 'francanglais',
        french_gloss: '', english_gloss: 'Reference meaning', match_type: 'exact',
        source: 'dictionary', source_document: 'fixture.md', source_line: 4, aliases: ['fixture'],
      }],
    })))
    const { user } = renderTranslator({ aiAvailable: false })
    await user.type(sourceText(), 'fixture')
    await user.click(screen.getByRole('checkbox', { name: 'Use approved dataset matches' }))
    expect(submit()).toBeEnabled()
    await user.click(submit())
    expect(await screen.findByText('Reference dictionary · local')).toBeInTheDocument()
    expect(screen.getByText(/fixture.md:4 · not fieldwork/)).toBeInTheDocument()
    expect(screen.getByText('No French gloss recorded')).toBeInTheDocument()
    expect(screen.getByText(/No Gemini translation request was needed/)).toBeInTheDocument()
    expect(screen.queryByText('Exact approved match · local')).not.toBeInTheDocument()
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toMatchObject({
      use_dataset: false, use_dictionary: true, allow_ai: false,
    })
  })

  it('sets the correct direction for a dictionary handoff without automatically submitting', async () => {
    renderTranslator({ incomingText: { id: 1, text: 'pasho', source: 'francanglais', target: 'en', kind: 'dictionary' } })
    expect(sourceText()).toHaveValue('pasho')
    expect(screen.getByLabelText('From')).toHaveValue('francanglais')
    expect(screen.getByLabelText('To')).toHaveValue('en')
    expect(screen.getByText(/A reference word is in your draft/)).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('invalidates an old answer when dictionary use changes', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(translation({ translation: 'Old source selection' })))
    const { user } = renderTranslator()
    await user.type(sourceText(), 'fixture')
    await user.click(submit())
    await screen.findByText('Old source selection')
    await user.click(screen.getByRole('checkbox', { name: 'Use reference dictionary' }))
    expect(screen.queryByText('Old source selection')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('works without AI, explicitly sends local-only options and identifies an exact approved match', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(translation({ translation: 'Local fixture result' })))
    const { user } = renderTranslator({ aiAvailable: false })
    expect(screen.getByRole('checkbox', { name: 'Allow AI suggestions for gaps' })).toBeDisabled()
    expect(submit()).toBeDisabled()
    await user.type(sourceText(), '  Sens de test  ')
    expect(fetch).not.toHaveBeenCalled()
    await user.click(submit())

    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toEqual({
      text: 'Sens de test', source_language: 'fr', target_language: 'francanglais',
      explanation_language: 'fr', tone: 'everyday', use_dataset: true, use_dictionary: true, allow_ai: false,
    })
    expect(await screen.findByText('Exact approved match · local')).toBeInTheDocument()
    expect(screen.getByText('Local fixture result')).toBeInTheDocument()
    expect(screen.getByText('ID: fixture-record-1')).toBeInTheDocument()
    expect(screen.queryByText(/^AI suggestion ·/)).not.toBeInTheDocument()
  })

  it.each([
    { origin: 'ai' as const, label: 'AI suggestion · no local evidence' },
    { origin: 'ai_with_dataset' as const, label: 'AI suggestion · with dataset matches' },
  ])('labels $origin without implying that retrieval verifies the answer', async ({ origin, label }) => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(translation({
      translation: 'Generated fixture answer', origin, evidence: origin === 'ai' ? [] : translation().evidence,
    })))
    const { user } = renderTranslator()
    await user.type(sourceText(), 'Unmatched fixture input')
    await user.click(submit())
    expect(await screen.findByText(label)).toBeInTheDocument()
    expect(screen.getByText(/These are retrieved records, not a verification of the entire AI answer/)).toBeInTheDocument()
    expect(screen.queryByText('Exact approved match · local')).not.toBeInTheDocument()
  })

  it('reports a local coverage gap rather than claiming a complete translation or AI answer', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(translation({
      translation: '', evidence: [], explanation: '',
      coverage: { matched_terms: [], unmatched_terms: ['unknown-fixture'], warnings: ['No approved full-entry match.'] },
    })))
    const { user } = renderTranslator({ aiAvailable: false })
    await user.type(sourceText(), 'unknown-fixture')
    await user.click(submit())
    expect(await screen.findByText('Local dataset lookup')).toBeInTheDocument()
    expect(screen.getByText(/No complete translation was found in the enabled local sources/)).toBeInTheDocument()
    expect(screen.getByText('unknown-fixture', { selector: 'dd' })).toBeInTheDocument()
    expect(screen.getByText('No approved full-entry match.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Copy text' })).not.toBeInTheDocument()
  })

  it('prevents requests when both lookup and AI are off, and resets results on direction changes', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(translation({ translation: 'Result to invalidate' })))
    const { user } = renderTranslator({ aiAvailable: false })
    await user.type(sourceText(), 'Fixture')
    await user.click(screen.getByRole('checkbox', { name: 'Use approved dataset matches' }))
    await user.click(screen.getByRole('checkbox', { name: 'Use reference dictionary' }))
    expect(submit()).toBeDisabled()
    expect(fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('checkbox', { name: 'Use approved dataset matches' }))
    await user.click(submit())
    expect(await screen.findByText('Result to invalidate')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Swap source and target languages' }))
    expect(screen.getByLabelText('From')).toHaveValue('francanglais')
    expect(screen.getByLabelText('To')).toHaveValue('fr')
    expect(screen.queryByText('Result to invalidate')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('preserves input after a service error, clears it on edit, and permits an explicit retry', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ detail: 'Translation service is temporarily unavailable.' }, 503))
      .mockResolvedValueOnce(jsonResponse(translation({ translation: 'Recovered fixture result' })))
    const { user } = renderTranslator()
    await user.type(sourceText(), 'Fixture')
    await user.click(submit())
    expect(await screen.findByRole('alert')).toHaveTextContent('Translation service is temporarily unavailable.')
    expect(sourceText()).toHaveValue('Fixture')
    await user.type(sourceText(), ' corrected')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledOnce()
    await user.click(submit())
    expect(await screen.findByText('Recovered fixture result')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('cancels on editing and ignores a stale response after a newer request succeeds', async () => {
    const old = deferred<Response>()
    vi.mocked(fetch)
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce(jsonResponse(translation({ translation: 'Current fixture result' })))
    const { user } = renderTranslator()
    await user.type(sourceText(), 'Old input')
    await user.click(submit())
    const oldSignal = vi.mocked(fetch).mock.calls[0]?.[1]?.signal
    expect(screen.getByRole('button', { name: /Translating/ })).toBeDisabled()
    await user.clear(sourceText())
    expect(oldSignal?.aborted).toBe(true)
    await user.type(sourceText(), 'Current input')
    await user.click(submit())
    expect(await screen.findByText('Current fixture result')).toBeInTheDocument()
    await act(async () => old.resolve(jsonResponse(translation({ translation: 'Stale fixture result' }))))
    expect(screen.getByText('Current fixture result')).toBeInTheDocument()
    expect(screen.queryByText('Stale fixture result')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('cancels when navigating away and does not display a response on return', async () => {
    const old = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(old.promise)
    const { user, rerender, props } = renderTranslator()
    await user.type(sourceText(), 'Preserved draft')
    await user.click(submit())
    rerender(<Translator {...props} active={false} />)
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
    await act(async () => old.resolve(jsonResponse(translation({ translation: 'Hidden stale answer' }))))
    rerender(<Translator {...props} active />)
    expect(sourceText()).toHaveValue('Preserved draft')
    expect(screen.queryByText('Hidden stale answer')).not.toBeInTheDocument()
    expect(submit()).toBeEnabled()
  })

  it('treats imported text as a bounded draft, not an automatic translation', () => {
    renderTranslator({ incomingText: { id: 1, text: 'x'.repeat(MAX_TEXT + 20) } })
    expect(sourceText()).toHaveValue('x'.repeat(MAX_TEXT))
    expect(screen.getByText(/Nothing has been submitted or saved/)).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })
})
