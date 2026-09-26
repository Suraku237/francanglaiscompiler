import { act, fireEvent, render, renderHook, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ReadButton } from '../../src/components'
import { RecordedReadings } from '../../src/RecordedReadings'
import { useReadAloud } from '../../src/voice'
import type { RecordedReading } from '../../src/voice'
import { audioFixtures } from '../audioFixtures'
import { ownership } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'
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
  await screen.findByText(saved ? 'Saved reading' : /No voice recording is available/)
  return { ...view, user, dialog }
}

describe('public read-only recorded playback without synthesis or recognition', () => {
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
    expect(within(dialog).getByText(/No voice recording is available/)).toHaveTextContent('read-only; recording and uploads are unavailable')
    expect(within(dialog).queryByRole('button', { name: /Record audio|Save voice recording|Upload/i })).not.toBeInTheDocument()
    expect(within(dialog).queryByLabelText('Attach an audio file')).not.toBeInTheDocument()
    expect(synthesis.speak).not.toHaveBeenCalled()
    expect(recognition).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledOnce()
  })

  it('never requests microphone permission for a missing recording', async () => {
    const { getUserMedia } = audioFixtures()
    const { recognition, synthesis } = speechFixtures()
    const { user, dialog } = await openReading()
    await user.click(within(dialog).getByRole('button', { name: 'Done' }))
    expect(getUserMedia).not.toHaveBeenCalled()
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

  it.each([false, true])('exposes playback only even with obsolete ownership flags: %s', async (canEdit) => {
    const { dialog } = await openReading(reading({ ownership: ownership({ owner_id: 'alice', owner_name: 'Alice', can_edit: canEdit }) }))
    expect(within(dialog).getByText('Public recording · Read-only.')).toBeVisible()
    expect(within(dialog).queryByText(/Creator:|Alice/)).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: /Record audio|Remove saved reading|Replace saved reading/ })).not.toBeInTheDocument()
    expect(within(dialog).queryByLabelText('Attach an audio file')).not.toBeInTheDocument()
  })

  it('does not treat a lookup failure as a missing recording, and provides an explicit retry', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Recording storage is unavailable.' }, 503))
    const user = userEvent.setup()
    render(<ReadingControls />)
    await user.click(screen.getByRole('button', { name: 'Read aloud with a recorded voice' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Recording storage is unavailable.')
    expect(screen.queryByText(/No voice recording is available/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save voice recording' })).not.toBeInTheDocument()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ reading: null }))
    await user.click(within(screen.getByRole('alert')).getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/No voice recording is available/)).toBeVisible()
  })

  it('keeps native controls usable after autoplay is blocked and surfaces real playback errors', async () => {
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new DOMException('Browser blocked autoplay', 'NotAllowedError'))
    const saved = reading()
    const { dialog } = await openReading(saved)
    const player = within(dialog).getByLabelText(`Play recording: ${saved.audio_filename}`)
    expect(player).toHaveAttribute('controls')
    expect(await within(dialog).findByText(/Use the play control to listen/)).toBeVisible()
    fireEvent.error(player)
    expect(within(dialog).getByRole('alert')).toHaveTextContent('could not be played')
    expect(within(dialog).queryByRole('button', { name: /Record audio|Upload/i })).not.toBeInTheDocument()
  })

  it('cancels lookup and ignores a late response after the dialog closes', async () => {
    const pending = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(pending.promise)
    const user = userEvent.setup()
    render(<ReadingControls />)
    await user.click(screen.getByRole('button', { name: 'Read aloud with a recorded voice' }))
    const signal = vi.mocked(fetch).mock.calls[0]?.[1]?.signal
    await user.click(screen.getByRole('button', { name: 'Done' }))
    expect(signal?.aborted).toBe(true)
    await act(async () => pending.resolve(jsonResponse({ reading: reading() })))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled()
  })
})
