import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Dictionary } from '../../src/Dictionary'
import type { DictionaryEntry, DictionaryResult } from '../../src/types'
import { deferred, jsonResponse } from '../helpers'

const record: DictionaryEntry = {
  id: 'dictionary:fixture.md:4', text: 'fixture / alias', aliases: ['fixture', 'alias'],
  language: 'francanglais', english_gloss: 'a test meaning', origin: 'Test source',
  topic: 'Test topic', source_document: 'fixture.md', source_line: 4,
}
const response = (overrides: Partial<DictionaryResult> = {}): DictionaryResult => ({
  entries: [record], total: 1, matched: 1, offset: 0, limit: 25, sources: ['fixture.md'], ...overrides,
})

describe('separate reference dictionary', () => {
  it('loads only when active and shows provenance without calling it collected fieldwork', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(response()))
    const props = { active: false, onTranslate: vi.fn() }
    const { rerender } = render(<Dictionary {...props} />)
    expect(fetch).not.toHaveBeenCalled()
    rerender(<Dictionary {...props} active />)
    expect(await screen.findByRole('heading', { name: record.text })).toBeInTheDocument()
    expect(screen.getByText('fixture.md:4')).toBeInTheDocument()
    expect(screen.getByText('a test meaning')).toBeInTheDocument()
    expect(screen.getByText('1 matching entry')).toBeInTheDocument()
    expect(screen.getByText(/No French translations were supplied/)).toBeInTheDocument()
    expect(screen.getByText(/not collected fieldwork/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next entries' })).toBeDisabled()
  })

  it('searches word forms or English meanings and resets pagination', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(response({ total: 60, matched: 60 })))
      .mockResolvedValueOnce(jsonResponse(response({ total: 60, matched: 60, offset: 25 })))
      .mockResolvedValueOnce(jsonResponse(response({ total: 60 })))
    const user = userEvent.setup()
    render(<Dictionary active onTranslate={vi.fn()} />)
    await screen.findByRole('heading', { name: record.text })
    await user.click(screen.getByRole('button', { name: 'Next entries' }))
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(String(vi.mocked(fetch).mock.calls[1]?.[0])).toContain('offset=25')
    await user.type(screen.getByRole('searchbox', { name: 'Search reference dictionary' }), 'test meaning')
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
    const url = new URL(String(vi.mocked(fetch).mock.calls[2]?.[0]), 'http://localhost')
    expect(url.searchParams.get('query')).toBe('test meaning')
    expect(url.searchParams.get('offset')).toBe('0')
    expect(url.searchParams.get('limit')).toBe('25')
  })

  it('opens a listed form as a draft only and never saves or submits it', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(response()))
    const onTranslate = vi.fn()
    const user = userEvent.setup()
    render(<Dictionary active onTranslate={onTranslate} />)
    await user.click(await screen.findByRole('button', { name: 'Open fixture / alias in translator' }))
    expect(onTranslate).toHaveBeenCalledWith('fixture')
    expect(fetch).toHaveBeenCalledOnce()
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain('/api/dictionary?')
  })

  it('reports an empty lookup without claiming the reference knows every word', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(response({ entries: [], matched: 0 })))
    render(<Dictionary active onTranslate={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'No dictionary entries found.' })).toBeInTheDocument()
    expect(screen.getByText(/does not mean the word is invalid/)).toBeInTheDocument()
  })

  it('surfaces a server error and allows an explicit retry', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ detail: 'Reference dictionary unavailable.' }, 503))
      .mockResolvedValueOnce(jsonResponse(response()))
    const user = userEvent.setup()
    render(<Dictionary active onTranslate={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Reference dictionary unavailable.')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: record.text })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('cancels an old lookup and ignores its response after a new search', async () => {
    const stale = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(stale.promise).mockResolvedValueOnce(jsonResponse(response()))
    const user = userEvent.setup()
    render(<Dictionary active onTranslate={vi.fn()} />)
    await waitFor(() => expect(fetch).toHaveBeenCalledOnce())
    const signal = vi.mocked(fetch).mock.calls[0]?.[1]?.signal
    await user.type(screen.getByRole('searchbox'), 'current')
    expect(signal?.aborted).toBe(true)
    await screen.findByRole('heading', { name: record.text })
    await act(async () => stale.resolve(jsonResponse(response({ entries: [{ ...record, text: 'Stale result' }] }))))
    expect(screen.queryByRole('heading', { name: 'Stale result' })).not.toBeInTheDocument()
  })
})
