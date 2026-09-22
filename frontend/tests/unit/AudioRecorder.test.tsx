import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AudioPlayer, AudioRecorder } from '../../src/AudioRecorder'
import { EntryEditor } from '../../src/Collection'
import { audioFixtures } from '../audioFixtures'
import { entry, metadata } from '../fixtures'
import { speechFixtures } from '../speechFixtures'
import { jsonResponse } from '../helpers'

describe('raw recording, manual transcription and attachment review', () => {
  it('uploads draft audio and entry fields together only after explicit save', async () => {
    audioFixtures()
    const user = userEvent.setup()
    const onSaved = vi.fn()
    render(<EntryEditor metadata={metadata} initialDraft={{ text: 'Synthetic test expression' }} onClose={vi.fn()} onSaved={onSaved} />)
    await user.click(screen.getByRole('button', { name: 'Record audio' }))
    expect(screen.getByRole('button', { name: 'Save unreviewed' })).toBeDisabled()
    expect(fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Stop recording' }))
    expect(await screen.findByText(/recording-\d+\.webm/)).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(entry({ audio_filename: 'stored.webm', review_status: 'unreviewed' })))
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    const request = vi.mocked(fetch).mock.calls[0]
    if (!request) throw new Error('Expected an audio save request')
    const [url, options] = request
    expect(url).toBe('/api/dataset/audio')
    expect(options?.body).toBeInstanceOf(FormData)
    const body = options?.body
    if (!(body instanceof FormData)) throw new Error('Expected multipart audio and fields')
    expect(body.get('file')).toBeInstanceOf(File)
    expect(JSON.parse(String(body.get('fields')))).toMatchObject({ text: 'Synthetic test expression', review_status: 'unreviewed' })
    expect(onSaved).toHaveBeenCalledOnce()
  })

  it('preserves the audio draft on failed save and clears approval after attachment selection', async () => {
    audioFixtures()
    const user = userEvent.setup()
    render(<EntryEditor entry={entry()} metadata={metadata} onClose={vi.fn()} onSaved={vi.fn()} />)
    await user.upload(screen.getByLabelText('Attach an audio file'), new File(['test audio'], 'fixture.wav', { type: 'audio/wav' }))
    expect(screen.getByRole('checkbox', { name: /I have reviewed/ })).not.toBeChecked()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Cannot save the local collection.' }, 500))
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot save')
    expect(screen.getByText(/fixture.wav \(/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save unreviewed' })).toBeEnabled()
  })

  it('detaches existing audio only when the edited entry is explicitly saved', async () => {
    audioFixtures()
    const user = userEvent.setup()
    render(<EntryEditor entry={entry({ audio_filename: 'existing.wav' })} metadata={metadata} onClose={vi.fn()} onSaved={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Remove attachment on save' }))
    expect(fetch).not.toHaveBeenCalled()
    expect(screen.getByText(/original file is retained locally/)).toBeInTheDocument()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(entry({ audio_filename: '', review_status: 'unreviewed' })))
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    const body = vi.mocked(fetch).mock.calls[0]?.[1]?.body
    if (!(body instanceof FormData)) throw new Error('Expected explicit removal form')
    expect(body.get('remove_audio')).toBe('true')
    expect(body.get('file')).toBeNull()
  })

  it('never fills the manual transcript from a recording or uploads an empty-text draft', async () => {
    audioFixtures()
    const { recognition } = speechFixtures()
    const user = userEvent.setup()
    render(<EntryEditor metadata={metadata} onClose={vi.fn()} onSaved={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Record audio' }))
    await user.click(screen.getByRole('button', { name: 'Stop recording' }))
    expect(await screen.findByText(/recording-\d+\.webm/)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /^Expression/ })).toHaveValue('')
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    expect(fetch).not.toHaveBeenCalled()
    expect(recognition).not.toHaveBeenCalled()
    expect(screen.getByText(/Listen and transcribe by hand/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /transcrib|dictat/i })).not.toBeInTheDocument()
  })

  it('revokes replaced preview URLs and surfaces playback errors', async () => {
    const { revokeObjectURL } = audioFixtures()
    const file = new File(['fixture'], 'fixture.wav')
    const props = { onFile: vi.fn(), file }
    const view = render(<AudioRecorder {...props} />)
    expect(screen.getByRole('link', { name: 'Download audio' })).toHaveAttribute('href', 'blob:synthetic-audio-fixture')
    view.rerender(<AudioRecorder {...props} file={null} />)
    expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:synthetic-audio-fixture')
    view.unmount()
    render(<AudioPlayer src="/api/dataset/test/audio" filename="missing.wav" />)
    fireEvent.error(screen.getByLabelText('Play recording: missing.wav'))
    expect(screen.getByRole('alert')).toHaveTextContent('could not be played')
    await act(async () => {})
  })
})
