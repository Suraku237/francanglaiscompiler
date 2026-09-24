import { act, render, renderHook, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ReadButton } from '../../src/components'
import { RecordedReadings } from '../../src/RecordedReadings'
import { useReadAloud } from '../../src/voice'
import type { RecordedReading } from '../../src/voice'
import { audioFixtures } from '../audioFixtures'
import { ownership } from '../fixtures'
import { jsonResponse, requestBody } from '../helpers'
import { speechFixtures } from '../speechFixtures'

function reading(overrides: Partial<RecordedReading> = {}): RecordedReading {
  return {
    id: 'cc7d8321-1c27-40ab-925a-fb61052fa853', text: '  Tchop\t', language: 'fr',
    audio_filename: 'a'.repeat(32) + '.wav',
    audio_url: '/api/readings/cc7d8321-1c27-40ab-925a-fb61052fa853/audio',
    created_at: '2026-09-24T12:00:00Z', updated_at: '2026-09-24T12:00:00Z',
    ownership: ownership(), ...overrides,
  }
}

function ReadingControls() {
  const speech = useReadAloud()
  return <><ReadButton speech={speech} id="reference" text={'  Tchop\t'} language="fr" /><RecordedReadings speech={speech} /></>
}

async function openReading(saved: RecordedReading | null = null) {
  vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ reading: saved }))
  const user = userEvent.setup()
  const view = render(<ReadingControls />)
  await user.click(screen.getByRole('button', { name: 'Read aloud with a recorded voice' }))
  const dialog = await screen.findByRole('dialog', { name: 'Recorded read-aloud' })
  await screen.findByText(saved ? 'Saved reading' : /No voice recording is saved/)
  return { ...view, user, dialog }
}

describe('shared recorded read-aloud without synthesis or recognition', () => {
  beforeEach(() => {
    audioFixtures()
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockImplementation(function (this: HTMLMediaElement) {
      Object.defineProperty(this, 'paused', { value: false, configurable: true })
      return Promise.resolve()
    })
    vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(function (this: HTMLMediaElement) {
      Object.defineProperty(this, 'paused', { value: true, configurable: true })
    })
  })

  it('selects exact text and language only on explicit action and never invokes synthetic voices', () => {
    const { synthesis, recognition } = speechFixtures()
    const { result } = renderHook(useReadAloud)
    expect(result.current.selection).toBeNull()
    act(() => result.current.speak('reference', '  Tchop\t', 'fr'))
    expect(result.current.selection).toEqual({ id: 'reference', text: '  Tchop\t', language: 'fr' })
    expect(result.current.activeId).toBe('reference')
    act(() => result.current.stop())
    expect(result.current.selection).toBeNull()
    expect(synthesis.speak).not.toHaveBeenCalled()
    expect(synthesis.getVoices).not.toHaveBeenCalled()
    expect(recognition).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it.each(['', ' \t', 'x'.repeat(4001)])('reports invalid reading text without querying or recording', (text) => {
    const { result } = renderHook(useReadAloud)
    act(() => result.current.speak('reference', text, 'fr'))
    expect(result.current.selection).toBeNull()
    expect(result.current.error).toContain('non-empty text of at most 4,000 characters')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('makes missing recordings explicit rather than using a browser voice', async () => {
    const { synthesis, recognition } = speechFixtures()
    const { dialog } = await openReading()
    expect(within(dialog).getByLabelText('Text for this reading').textContent).toBe('  Tchop\t')
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toEqual({ text: '  Tchop\t', language: 'fr' })
    expect(within(dialog).getByRole('button', { name: 'Record audio' })).toBeEnabled()
    expect(within(dialog).getByRole('button', { name: 'Save voice recording' })).toBeDisabled()
    expect(synthesis.speak).not.toHaveBeenCalled()
    expect(recognition).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('requires consent and uploads only the explicit saved recording, not a Collection entry', async () => {
    const { user, dialog } = await openReading()
    const file = new File(['Synthetic unit fixture audio'], 'my-reading.wav', { type: 'audio/wav' })
    await user.upload(within(dialog).getByLabelText('Attach an audio file'), file)
    expect(fetch).toHaveBeenCalledOnce()
    expect(within(dialog).getByRole('button', { name: 'Save voice recording' })).toBeDisabled()
    await user.click(within(dialog).getByRole('checkbox', { name: /permission to share/ }))
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(reading(), 201))
    await user.click(within(dialog).getByRole('button', { name: 'Save voice recording' }))
    expect(await within(dialog).findByText(/Your voice recording is saved/)).toBeVisible()
    const request = vi.mocked(fetch).mock.calls[1]
    expect(request?.[0]).toBe('/api/readings/audio')
    const form = request?.[1]?.body
    if (!(form instanceof FormData)) throw new Error('Expected a real multipart recording request.')
    expect(form.get('file')).toBe(file)
    expect(JSON.parse(String(form.get('fields')))).toEqual({ text: '  Tchop\t', language: 'fr', share_consent: true })
    expect(within(dialog).queryByText(/my-reading.wav \(/)).not.toBeInTheDocument()
    expect(within(dialog).getByRole('checkbox', { name: /permission to share/ })).not.toBeChecked()
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/dataset') || String(url).includes('/analyzer'))).toBe(false)
  })

  it('keeps microphone capture local until stopped and explicitly saved', async () => {
    const { track, getUserMedia } = audioFixtures()
    const { recognition, synthesis } = speechFixtures()
    const { user, dialog } = await openReading()
    await user.click(within(dialog).getByRole('button', { name: 'Record audio' }))
    expect(getUserMedia).toHaveBeenCalledOnce()
    expect(within(dialog).getByRole('button', { name: 'Save voice recording' })).toBeDisabled()
    expect(fetch).toHaveBeenCalledOnce()
    await user.click(within(dialog).getByRole('button', { name: 'Stop recording' }))
    expect(await within(dialog).findByText(/recording-\d+\.webm/)).toBeVisible()
    expect(track.stop).toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledOnce()
    expect(recognition).not.toHaveBeenCalled()
    expect(synthesis.speak).not.toHaveBeenCalled()
  })

  it('plays saved audio and stops playback when the reading dialog closes', async () => {
    const { synthesis } = speechFixtures()
    const saved = reading()
    const { user, dialog } = await openReading(saved)
    expect(within(dialog).getByLabelText(`Play recording: ${saved.audio_filename}`)).toHaveAttribute('src', saved.audio_url)
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: 'Done' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled()
    expect(synthesis.speak).not.toHaveBeenCalled()
  })

  it('lets another creator be heard but exposes no record, replacement or deletion controls', async () => {
    const { dialog } = await openReading(reading({ ownership: ownership({ owner_id: 'alice', owner_name: 'Alice', can_edit: false }) }))
    expect(within(dialog).getByText(/Creator: Alice/)).toHaveTextContent('Only its creator can replace or remove it.')
    expect(within(dialog).queryByRole('button', { name: /Record audio|Remove saved reading|Replace saved reading/ })).not.toBeInTheDocument()
    expect(within(dialog).queryByLabelText('Attach an audio file')).not.toBeInTheDocument()
  })

  it('does not treat a lookup failure as a missing recording, and provides an explicit retry', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Recording storage is unavailable.' }, 503))
    const user = userEvent.setup()
    render(<ReadingControls />)
    await user.click(screen.getByRole('button', { name: 'Read aloud with a recorded voice' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Recording storage is unavailable.')
    expect(screen.queryByText(/No voice recording is saved/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save voice recording' })).not.toBeInTheDocument()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ reading: null }))
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/No voice recording is saved/)).toBeVisible()
  })

  it('retains draft audio on failed upload and confirms before discarding it', async () => {
    const { user, dialog } = await openReading()
    await user.upload(within(dialog).getByLabelText('Attach an audio file'), new File(['fixture'], 'retry.wav', { type: 'audio/wav' }))
    await user.click(within(dialog).getByRole('checkbox', { name: /permission to share/ }))
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'The audio file is incomplete.' }, 422))
    await user.click(within(dialog).getByRole('button', { name: 'Save voice recording' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The audio file is incomplete.')
    expect(within(dialog).getByText(/retry.wav \(/)).toBeVisible()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await user.click(within(dialog).getByRole('button', { name: 'Done' }))
    expect(dialog).toBeVisible()
    confirm.mockReturnValue(true)
    await user.click(within(dialog).getByRole('button', { name: 'Done' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('requires explicit confirmation before removing a saved reading', async () => {
    const saved = reading()
    const { user, dialog } = await openReading(saved)
    await user.click(within(dialog).getByRole('button', { name: 'Remove saved reading' }))
    expect(fetch).toHaveBeenCalledOnce()
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 204 }))
    await user.click(within(dialog).getByRole('button', { name: 'Yes, remove reading' }))
    expect(await within(dialog).findByText(/The active reading was removed/)).toBeVisible()
    expect(vi.mocked(fetch).mock.calls[1]?.[0]).toBe(`/api/readings/${saved.id}`)
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.method).toBe('DELETE')
    expect(within(dialog).getByText(/No voice recording is saved/)).toBeVisible()
  })
})
