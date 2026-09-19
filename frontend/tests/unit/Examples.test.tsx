import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Examples } from '../../src/Examples'
import { Translator } from '../../src/Translator'
import type { PracticeResult } from '../../src/types'
import { jsonResponse, requestBody } from '../helpers'
import { translation } from '../fixtures'

const reference: PracticeResult = {
  entries: [{
    id: 'examples:fixture:1', text: 'Mon mbom, tu es where?', language: 'francanglais',
    french_gloss: 'Mon pote, tu es où ?', english_gloss: 'My guy, where are you?',
    topic: 'People', notes: 'Constructed example; not a recorded statement.',
    source_document: 'camfranglais_statements.csv', source_line: 2, constructed: true,
  }],
  total: 26, matched: 1, offset: 0, limit: 25, sources: ['camfranglais_statements.csv'],
}

describe('separate constructed practice material', () => {
  it('shows original bilingual meanings, provenance and explicit draft-only handoff', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(reference))
    const onTranslate = vi.fn()
    const user = userEvent.setup()
    render(<Examples active onTranslate={onTranslate} />)
    expect(await screen.findByRole('heading', { name: 'Mon mbom, tu es where?' })).toBeInTheDocument()
    expect(screen.getByText('Mon pote, tu es où ?')).toBeInTheDocument()
    expect(screen.getByText('My guy, where are you?')).toBeInTheDocument()
    expect(screen.getByText('camfranglais_statements.csv:2')).toBeInTheDocument()
    expect(screen.getByText('Constructed examples, not genuine fieldwork.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Practice in French' }))
    expect(onTranslate).toHaveBeenCalledExactlyOnceWith('Mon mbom, tu es where?', 'fr')
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('does not load while inactive and supports an explicit retry', async () => {
    const props = { active: false, onTranslate: vi.fn() }
    const view = render(<Examples {...props} />)
    expect(fetch).not.toHaveBeenCalled()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Practice source unavailable.' }, 503))
    view.rerender(<Examples {...props} active />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Practice source unavailable.')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(reference))
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Mon mbom, tu es where?' })).toBeInTheDocument()
  })

  it('keeps examples off by default and enables them only for an explicit practice handoff', async () => {
    const props = {
      active: true, aiAvailable: false,
      speech: { supported: false, activeId: null, error: '', stop: vi.fn(), speak: vi.fn() },
      onOpenAssistant: vi.fn(), onOpenCollection: vi.fn(), onOpenImports: vi.fn(),
    }
    const view = render(<Translator {...props} />)
    const source = screen.getByRole('checkbox', { name: 'Use constructed practice examples (not fieldwork)' })
    expect(source).not.toBeChecked()
    view.rerender(<Translator {...props} incomingText={{
      id: 1, text: 'Mon mbom, tu es where?', source: 'francanglais', target: 'fr', kind: 'examples',
    }} />)
    expect(source).toBeChecked()
    expect(fetch).not.toHaveBeenCalled()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(translation({
      translation: 'Mon pote, tu es où ?', origin: 'examples', model: 'local-examples',
      source_language: 'francanglais', target_language: 'fr',
    })))
    await userEvent.setup().click(screen.getByRole('button', { name: 'Translate' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toMatchObject({
      text: 'Mon mbom, tu es where?', use_examples: true, allow_ai: false,
      source_language: 'francanglais', target_language: 'fr',
    })
    expect(await screen.findByText('Constructed practice example · local')).toBeInTheDocument()
  })
})
