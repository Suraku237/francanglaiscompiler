import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Coursework } from '../../src/Coursework'
import { courseworkAnalysis, courseworkState, manualParse, project } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'

async function renderLab() {
  vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(courseworkState()))
  const view = render(<Coursework active aiAvailable={false} />)
  await screen.findByLabelText('Context-free grammar')
  return { ...view, user: userEvent.setup() }
}

const grammarInput = () => screen.getByLabelText('Context-free grammar')
const saveButton = () => screen.getByRole('button', { name: 'Save project' })
const exportButton = () => screen.getByRole('button', { name: 'Download coursework draft (.zip)' })

async function replaceText(user: ReturnType<typeof userEvent.setup>, input: HTMLElement, value: string) {
  await user.clear(input)
  await user.click(input)
  await user.paste(value)
}

describe('coursework draft, computation and persistence boundaries', () => {
  it('analyzes the editor grammar without saving, blocks dirty exports and invalidates results on grammar edits', async () => {
    const { user } = await renderLab()
    await replaceText(user, grammarInput(), 'S -> NOUN\nTail -> epsilon')
    expect(screen.getByText('Unsaved project changes')).toBeInTheDocument()
    expect(exportButton()).toBeDisabled()

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(courseworkAnalysis()))
    await user.click(screen.getByRole('button', { name: 'Analyze grammar & saved corpus' }))
    expect(await screen.findByRole('heading', { name: 'Computed grammar' })).toBeInTheDocument()
    expect(requestBody(vi.mocked(fetch).mock.calls[1])).toEqual({ grammar: 'S -> NOUN\nTail -> epsilon' })
    expect(vi.mocked(fetch).mock.calls[1]?.[0]).toBe('/api/coursework/analyze')
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(false)
    expect(exportButton()).toBeDisabled()

    await replaceText(user, grammarInput(), 'S -> NOUN\nTail -> epsilon\nExtra -> VERB')
    expect(screen.queryByRole('heading', { name: 'Computed grammar' })).not.toBeInTheDocument()
    expect(screen.getByText(/Grammar edited: previous computations have been cleared/)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('saves a snapshot, but edits made while saving remain dirty after the evidence refresh', async () => {
    const { user } = await renderLab()
    await replaceText(user, screen.getByLabelText('Group member 1'), 'Fixture learner')
    const snapshot = project({ group_members: ['Fixture learner', '', ''] })
    const saving = deferred<Response>()
    vi.mocked(fetch)
      .mockReturnValueOnce(saving.promise)
      .mockResolvedValueOnce(jsonResponse(courseworkState(snapshot)))
    await user.click(saveButton())
    expect(requestBody(vi.mocked(fetch).mock.calls[1])).toEqual(snapshot)
    expect(exportButton()).toBeDisabled()
    expect(screen.getByRole('button', { name: /Saving coursework project/ })).toBeDisabled()

    await replaceText(user, screen.getByLabelText('Linguistic discussion'), 'Later unsaved writing')
    await act(async () => saving.resolve(jsonResponse({ saved: true })))
    expect(await screen.findByText(/Project saved locally, including the grammar/)).toBeInTheDocument()
    expect(screen.getByLabelText('Linguistic discussion')).toHaveValue('Later unsaved writing')
    expect(screen.getByText('Unsaved project changes')).toBeInTheDocument()
    expect(exportButton()).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('enables export only after saving and refreshing the matching draft', async () => {
    const { user } = await renderLab()
    await replaceText(user, screen.getByLabelText('Limitations & critical evaluation'), 'Fixture limitation')
    const savedProject = project({ limitations: 'Fixture limitation' })
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ saved: true }))
      .mockResolvedValueOnce(jsonResponse(courseworkState(savedProject)))
    await user.click(saveButton())
    expect(await screen.findByText('No unsaved editor changes')).toBeInTheDocument()
    expect(exportButton()).toBeEnabled()
    expect(vi.mocked(fetch).mock.calls[1]?.[0]).toBe('/api/coursework/project')
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.method).toBe('PUT')
    expect(requestBody(vi.mocked(fetch).mock.calls[1])).toEqual(savedProject)
    expect(vi.mocked(fetch).mock.calls.some(([url]) => url === '/api/coursework/export')).toBe(false)
  })

  it('retains the draft on failed saves and keeps export blocked', async () => {
    const { user } = await renderLab()
    await replaceText(user, screen.getByLabelText('Group member 1'), 'Unsaved fixture learner')
    vi.mocked(fetch).mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await user.click(saveButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('The change may have completed.')
    expect(screen.getByRole('alert')).toHaveTextContent('Refresh the saved coursework evidence')
    expect(screen.getByLabelText('Group member 1')).toHaveValue('Unsaved fixture learner')
    expect(screen.getByText('Unsaved project changes')).toBeInTheDocument()
    expect(exportButton()).toBeDisabled()
  })

  it('refreshes saved evidence without replacing editor text and warns before unloading dirty work', async () => {
    const { user } = await renderLab()
    const cleanUnload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(cleanUnload)
    expect(cleanUnload.defaultPrevented).toBe(false)

    await replaceText(user, grammarInput(), 'S -> NOUN\nTail -> epsilon')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(courseworkState(project({ discussion: 'Saved elsewhere' }))))
    await user.click(screen.getByRole('button', { name: 'Refresh saved coursework evidence, preserve editor draft' }))
    expect(await screen.findByText(/Evidence refreshed without replacing your editor draft/)).toBeInTheDocument()
    expect(grammarInput()).toHaveValue('S -> NOUN\nTail -> epsilon')
    expect(screen.getByLabelText('Linguistic discussion')).toHaveValue('')
    const dirtyUnload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(dirtyUnload)
    expect(dirtyUnload.defaultPrevented).toBe(true)
  })

  it('allows an explicit empty parser test and clears its trace when the input changes', async () => {
    const { user } = await renderLab()
    await replaceText(user, grammarInput(), 'S -> epsilon')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(manualParse()))
    await user.click(screen.getByRole('button', { name: 'Parse test input' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[1])).toEqual({ grammar: 'S -> epsilon', text: '' })
    expect(vi.mocked(fetch).mock.calls[1]?.[0]).toBe('/api/coursework/parse')
    expect(await screen.findByRole('heading', { name: 'Manual test result' })).toBeInTheDocument()
    expect(screen.getByText('ACCEPT', { exact: true })).toBeInTheDocument()
    expect(screen.getByText('S → epsilon')).toBeInTheDocument()
    await replaceText(user, screen.getByLabelText('Manual parser test'), 'Unsaved manual input')
    expect(screen.queryByRole('heading', { name: 'Manual test result' })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('cancels analysis on navigation and ignores its stale result while preserving the draft', async () => {
    const { user, rerender } = await renderLab()
    await replaceText(user, screen.getByLabelText('Group member 1'), 'Draft member')
    const oldAnalysis = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(oldAnalysis.promise)
    await user.click(screen.getByRole('button', { name: 'Analyze grammar & saved corpus' }))
    rerender(<Coursework active={false} aiAvailable={false} />)
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.signal?.aborted).toBe(true)
    await act(async () => oldAnalysis.resolve(jsonResponse(courseworkAnalysis())))
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(courseworkState()))
    rerender(<Coursework active aiAvailable={false} />)
    expect(screen.getByLabelText('Group member 1')).toHaveValue('Draft member')
    expect(screen.queryByRole('heading', { name: 'Computed grammar' })).not.toBeInTheDocument()
    expect(screen.getByText(/your editor draft is kept/)).toBeInTheDocument()
  })
})
