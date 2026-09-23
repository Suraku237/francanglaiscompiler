import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Examples } from '../../src/Examples'
import type { PracticeResult } from '../../src/types'
import { jsonResponse } from '../helpers'

const reference: PracticeResult = {
  entries: [{
    id: 'examples:fixture:1', text: 'Mon mbom, tu es where?', language: 'francanglais',
    french_gloss: 'Mon pote, tu es où ?', english_gloss: 'My guy, where are you?',
    topic: 'People', notes: 'Constructed example; not a recorded statement.',
    source_document: 'camfranglais_statements.csv', source_line: 2, constructed: true,
  }],
  total: 26, matched: 1, offset: 0, limit: 25, sources: ['camfranglais_statements.csv'],
}

describe('synthetic reference material', () => {
  it('shows original meanings and provenance, with only an explicit manual compiler handoff', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(reference))
    const onUseText = vi.fn()
    const user = userEvent.setup()
    render(<Examples active onUseText={onUseText} />)
    expect(await screen.findByRole('heading', { name: 'Mon mbom, tu es where?' })).toBeInTheDocument()
    expect(screen.getByText('Mon pote, tu es où ?')).toBeInTheDocument()
    expect(screen.getByText('My guy, where are you?')).toBeInTheDocument()
    expect(screen.getByText('camfranglais_statements.csv:2')).toBeInTheDocument()
    expect(screen.getByText('Constructed examples, not genuine fieldwork.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Open in Franc Analyzer' }))
    expect(onUseText).toHaveBeenCalledExactlyOnceWith('Mon mbom, tu es where?')
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: /translate|save|approve/i })).not.toBeInTheDocument()
  })

  it('does not load while inactive and supports an explicit retry', async () => {
    const props = { active: false, onUseText: vi.fn() }
    const view = render(<Examples {...props} />)
    expect(fetch).not.toHaveBeenCalled()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Practice source unavailable.' }, 503))
    view.rerender(<Examples {...props} active />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Practice source unavailable.')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(reference))
    await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'Mon mbom, tu es where?' })).toBeInTheDocument()
  })
})
