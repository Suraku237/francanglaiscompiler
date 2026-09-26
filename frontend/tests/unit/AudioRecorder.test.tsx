import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { AudioPlayer, AudioRecorder } from '../../src/AudioRecorder'
import { EntryViewer } from '../../src/Collection'
import { audioFixtures } from '../audioFixtures'
import { entry } from '../fixtures'
import { speechFixtures } from '../speechFixtures'

describe('audio playback and local preview', () => {
  it('offers only the existing recording in public Collection, never microphone capture or uploads', () => {
    const { getUserMedia } = audioFixtures()
    const { recognition, synthesis } = speechFixtures()
    render(<EntryViewer entry={entry({ audio_filename: 'saved.wav' })} onClose={vi.fn()} />)
    expect(screen.getByLabelText('Play recording: saved.wav')).toHaveAttribute('src', '/api/dataset/fixture-record-1/audio')
    expect(screen.getByRole('link', { name: 'Download audio' })).toBeVisible()
    expect(screen.queryByRole('button', { name: /record|save|upload|remove/i })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Attach an audio file')).not.toBeInTheDocument()
    expect(getUserMedia).not.toHaveBeenCalled()
    expect(recognition).not.toHaveBeenCalled()
    expect(synthesis.speak).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
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
