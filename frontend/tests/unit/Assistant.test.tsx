import type { ComponentProps } from 'react'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Assistant } from '../../src/Assistant'
import type { HistoryItem, SavedConversation } from '../../src/accountTypes'
import { MAX_TEXT } from '../../src/types'
import type { ChatMessage } from '../../src/types'
import type { ReadAloud } from '../../src/voice'
import { setupAssistantBrowser } from '../assistantFixtures'
import { chatReply } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'

setupAssistantBrowser()

function renderAssistant(overrides: Partial<ComponentProps<typeof Assistant>> = {}) {
  const speech: ReadAloud = { supported: false, activeId: null, error: '', speak: vi.fn(), stop: vi.fn() }
  const props = { active: true, aiAvailable: true, speech, ...overrides }
  return { ...render(<Assistant {...props} />), props, user: userEvent.setup() }
}

const draft = () => screen.getByRole('textbox', { name: 'Message for the assistant' })
const send = () => screen.getByRole('button', { name: 'Send' })

describe('assistant conversation contracts', () => {
  it('sends explicit language and source controls, preserves newlines and never saves automatically', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(chatReply({ reply: 'English fixture answer.' })))
    const { user, props } = renderAssistant()
    await user.click(within(screen.getByRole('group', { name: 'Assistant explanation language' })).getByRole('button', { name: 'English EN' }))
    await user.selectOptions(screen.getByLabelText('To'), 'en')
    await user.selectOptions(screen.getByLabelText('From'), 'fr')
    await user.click(screen.getByRole('checkbox', { name: 'Use approved terminology for this answer' }))
    await user.click(screen.getByRole('checkbox', { name: 'Use reference dictionary for this answer' }))
    await user.type(draft(), '  Synthetic client message.')
    await user.keyboard('{Shift>}{Enter}{/Shift}More context.  ')
    expect(fetch).not.toHaveBeenCalled()
    await user.keyboard('{Enter}')

    expect(await screen.findByText('English fixture answer.')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/chat', expect.objectContaining({ method: 'POST' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toEqual({
      message: 'Synthetic client message.\nMore context.', language: 'en', history: [],
      use_dataset: false, use_dictionary: false, source_language: 'fr', target_language: 'en',
    })
    expect(screen.getByText('AI suggestion \u00b7 no local evidence')).toBeInTheDocument()
    expect(screen.getByText('French \u2192 English \u00b7 Explanations: English')).toBeInTheDocument()
    expect(draft()).toHaveValue('')
    expect(send()).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Save conversation' })).toBeEnabled()
    expect(props.speech.speak).not.toHaveBeenCalled()
  })

  it('keeps a failed draft, surfaces provider quota errors and retries without remembering failed exchanges', async () => {
    const quotaError = 'Gemini quota or rate limit reached. Check your quota or try later.'
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(chatReply({ reply: 'First successful reply.' })))
      .mockResolvedValueOnce(jsonResponse({ detail: quotaError }, 429))
      .mockResolvedValueOnce(jsonResponse(chatReply({ reply: 'Successful retry.' })))
    const { user } = renderAssistant()
    await user.type(draft(), 'First synthetic question.')
    await user.click(send())
    await screen.findByText('First successful reply.')
    await user.type(draft(), 'Synthetic follow-up.')
    await user.click(send())

    expect(await screen.findByRole('alert')).toHaveTextContent(quotaError)
    expect(draft()).toHaveValue('Synthetic follow-up.')
    expect(screen.getAllByRole('article', { name: 'Your message' })).toHaveLength(1)
    expect(screen.getAllByRole('article', { name: 'Assistant reply' })).toHaveLength(1)
    expect(send()).toBeEnabled()
    expect(fetch).toHaveBeenCalledTimes(2)
    await user.click(send())

    expect(await screen.findByText('Successful retry.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(requestBody(vi.mocked(fetch).mock.calls[2])).toEqual(requestBody(vi.mocked(fetch).mock.calls[1]))
    expect(requestBody(vi.mocked(fetch).mock.calls[2])).toMatchObject({
      history: [
        { role: 'user', content: 'First synthetic question.' },
        { role: 'assistant', content: 'First successful reply.' },
      ],
    })
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('sends only the six most recent successful exchanges while keeping the displayed conversation', async () => {
    const { user } = renderAssistant()
    const exchanges: ChatMessage[] = []
    for (let index = 1; index <= 8; index++) {
      const message = `Synthetic question ${index}.`
      const reply = `Synthetic reply ${index}.`
      vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(chatReply({ reply })))
      fireEvent.change(draft(), { target: { value: message } })
      await user.click(send())
      await screen.findByText(reply)
      expect(requestBody(vi.mocked(fetch).mock.calls[index - 1])).toMatchObject({ history: exchanges.slice(-12) })
      exchanges.push({ role: 'user', content: message }, { role: 'assistant', content: reply })
    }
    expect(screen.getAllByRole('article', { name: 'Assistant reply' })).toHaveLength(8)
    expect(fetch).toHaveBeenCalledTimes(8)
  })

  it('accepts exactly 24000 history characters and removes complete oldest exchanges above the limit', async () => {
    const { user } = renderAssistant()
    const exchanges: ChatMessage[] = []
    for (let index = 1; index <= 5; index++) {
      const message = `Synthetic question ${index}.`.padEnd(MAX_TEXT, 'x')
      const reply = `Synthetic reply ${index}.`.padEnd(MAX_TEXT, 'y')
      vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(chatReply({ reply })))
      fireEvent.change(draft(), { target: { value: message } })
      await user.click(send())
      await screen.findByText(reply)
      expect(requestBody(vi.mocked(fetch).mock.calls[index - 1])).toMatchObject({ history: exchanges.slice(-6) })
      exchanges.push({ role: 'user', content: message }, { role: 'assistant', content: reply })
    }
    expect(requestBody(vi.mocked(fetch).mock.calls[3])).toMatchObject({ history: exchanges.slice(0, 6) })
    expect(requestBody(vi.mocked(fetch).mock.calls[4])).toMatchObject({ history: exchanges.slice(2, 8) })
    expect(screen.getAllByRole('article', { name: 'Assistant reply' })).toHaveLength(5)
  })

  it.each(['Cancel', 'Clear conversation'])('handles %s during a request without accepting stale replies or losing a new draft', async (action) => {
    const pending = deferred<Response>()
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(chatReply({ reply: 'Existing successful reply.' })))
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce(jsonResponse(chatReply({ reply: 'New successful reply.' })))
    const { user } = renderAssistant()
    await user.type(draft(), 'Existing successful question.')
    await user.click(send())
    await screen.findByText('Existing successful reply.')
    await user.type(draft(), 'Pending question.')
    await user.click(send())
    const signal = vi.mocked(fetch).mock.calls[1]?.[1]?.signal
    expect(signal?.aborted).toBe(false)
    expect(draft()).toBeDisabled()
    expect(screen.getByLabelText('From')).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'Use approved terminology for this answer' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: action }))

    expect(signal?.aborted).toBe(true)
    expect(draft()).toBeEnabled()
    expect(draft()).toHaveValue(action === 'Cancel' ? 'Pending question.' : '')
    expect(screen.queryAllByRole('article', { name: 'Assistant reply' })).toHaveLength(action === 'Cancel' ? 1 : 0)
    fireEvent.change(draft(), { target: { value: 'New question after cancellation.' } })
    await act(async () => pending.resolve(jsonResponse(chatReply({ reply: 'Stale cancelled reply.' }))))
    expect(screen.queryByText('Stale cancelled reply.')).not.toBeInTheDocument()
    expect(draft()).toHaveValue('New question after cancellation.')
    await user.click(send())
    await screen.findByText('New successful reply.')
    expect(requestBody(vi.mocked(fetch).mock.calls[2])).toMatchObject({
      history: action === 'Cancel' ? [
        { role: 'user', content: 'Existing successful question.' },
        { role: 'assistant', content: 'Existing successful reply.' },
      ] : [],
    })
  })

  it('saves only after an explicit click and preserves the conversation when a save fails', async () => {
    const message = 'Synthetic conversation for explicit saving. '.padEnd(140, 'x')
    const reply = 'Synthetic reply for explicit saving.'
    const content: SavedConversation = { messages: [{ role: 'user', content: message }, { role: 'assistant', content: reply }] }
    const saved: HistoryItem = {
      id: 'fixture-history-1', kind: 'conversation', title: message.slice(0, 100), content,
      created_at: '2026-01-01T12:00:00Z', updated_at: '2026-01-01T12:00:00Z',
    }
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(chatReply({ reply })))
      .mockResolvedValueOnce(jsonResponse({ detail: 'The saved-history store is unavailable.' }, 503))
      .mockResolvedValueOnce(jsonResponse(saved, 201))
    const { user } = renderAssistant()
    fireEvent.change(draft(), { target: { value: message } })
    await user.click(send())
    await screen.findByText(reply)
    expect(fetch).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Save conversation' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The saved-history store is unavailable.')
    expect(screen.getByText(reply)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
    await user.click(screen.getByRole('button', { name: 'Save conversation' }))

    expect(await screen.findByRole('button', { name: 'Saved to history' })).toBeDisabled()
    expect(screen.getByText('Saved privately in this project.')).toHaveAttribute('role', 'status')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenLastCalledWith('/api/workspace/history', expect.objectContaining({ method: 'POST' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[2])).toEqual({
      kind: 'conversation', title: message.slice(0, 100), content,
    })
    expect(requestBody(vi.mocked(fetch).mock.calls[2])).toEqual(requestBody(vi.mocked(fetch).mock.calls[1]))
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('does not submit without configured AI or a nonblank message', async () => {
    const { user, props, rerender } = renderAssistant({ aiAvailable: false })
    await user.type(draft(), 'Synthetic draft without AI.')
    expect(send()).toBeDisabled()
    expect(screen.getByText(/The assistant requires AI configuration/)).toBeInTheDocument()
    await user.keyboard('{Enter}')
    expect(fetch).not.toHaveBeenCalled()
    rerender(<Assistant {...props} aiAvailable />)
    expect(send()).toBeEnabled()
    fireEvent.change(draft(), { target: { value: '   ' } })
    expect(send()).toBeDisabled()
    await user.keyboard('{Enter}')
    expect(fetch).not.toHaveBeenCalled()
  })
})
