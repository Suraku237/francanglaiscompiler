import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SavedWork } from '../../src/SavedWork'
import type { HistoryItem } from '../../src/accountTypes'
import { jsonResponse } from '../helpers'

const item: HistoryItem = {
  id: 'legacy-fixture', kind: 'translation', title: 'Legacy fixture',
  created_at: '2026-01-01T12:00:00Z', updated_at: '2026-01-01T12:00:00Z',
  content: {
    source_text: '  Mbom,\tTu  es where?\n\n', source_language: 'francanglais', target_language: 'en',
    translation: 'Synthetic saved output', explanation: 'Unverified old fixture', note: 'Not fieldwork',
  },
}

async function openHistory(record: HistoryItem = item) {
  vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ entries: [record] })).mockResolvedValueOnce(jsonResponse(record))
  const user = userEvent.setup()
  const onUseText = vi.fn()
  render(<SavedWork active onUseText={onUseText} />)
  await user.click(await screen.findByRole('button', { name: `Open ${record.title}` }))
  return { user, onUseText }
}

describe('preserved legacy history', () => {
  it('keeps old text readable and hands the source unchanged to the compiler without generation or saving', async () => {
    const { user, onUseText } = await openHistory()
    expect(screen.getByLabelText('Saved work details')).toHaveTextContent('Synthetic saved output')
    expect(screen.getByText(/Historical content may contain generated or unverified material/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Use source in compiler' }))
    expect(onUseText).toHaveBeenCalledExactlyOnceWith('  Mbom,\tTu  es where?\n\n')
    expect(vi.mocked(fetch).mock.calls.map(([url]) => url)).toEqual(['/api/workspace/history', '/api/workspace/history/legacy-fixture'])
    expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true)
    expect(screen.queryByRole('button', { name: /translate|send|Ask AI/i })).not.toBeInTheDocument()
  })

  it('hands off the last user message, never a generated conversation reply', async () => {
    const { user, onUseText } = await openHistory({
      ...item, kind: 'conversation', content: { messages: [
        { role: 'user', content: 'Earlier question' },
        { role: 'assistant', content: 'Earlier unverified reply' },
        { role: 'user', content: '  Latest user text\n' },
        { role: 'assistant', content: 'Unverified output to retain in history only' },
      ] },
    })
    expect(screen.getAllByText('Legacy assistant reply')).toHaveLength(2)
    await user.click(screen.getByRole('button', { name: 'Use source in compiler' }))
    expect(onUseText).toHaveBeenCalledExactlyOnceWith('  Latest user text\n')
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('retains explicit rename, export and deletion controls without creating new saved items', async () => {
    const { user } = await openHistory()
    const create = vi.fn(() => 'blob:legacy-export')
    vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await user.click(screen.getByRole('button', { name: 'Download saved work' }))
    expect(create).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledTimes(2)
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ ...item, title: 'Renamed legacy fixture' }))
      .mockResolvedValueOnce(jsonResponse({ entries: [{ ...item, title: 'Renamed legacy fixture' }] }))
    await user.clear(screen.getByLabelText('Saved title'))
    await user.type(screen.getByLabelText('Saved title'), 'Renamed legacy fixture')
    await user.click(screen.getByRole('button', { name: 'Rename saved work' }))
    expect(await screen.findByRole('heading', { name: 'Renamed legacy fixture' })).toBeInTheDocument()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse({ entries: [] }))
    await user.click(screen.getByRole('button', { name: 'Delete saved work' }))
    expect(await screen.findByRole('heading', { name: 'No legacy saved work' })).toBeInTheDocument()
    expect(vi.mocked(fetch).mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
  })
})
