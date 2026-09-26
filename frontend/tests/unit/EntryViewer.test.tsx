import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EntryViewer } from '../../src/Collection'
import { entry, ownership } from '../fixtures'

describe('read-only Collection details', () => {
  it.each([false, true])('preserves original data and playback without trusting obsolete edit flags: %s', async (canEdit) => {
    const original = entry({
      id: 'fixture/id with spaces', text: '  Exact\tshared text\n',
      contributor: 'Original field contributor', source_location: 'Original place',
      audio_filename: 'shared.wav',
      ownership: ownership({ owner_id: 'historical-id', owner_name: 'Historical name', can_edit: canEdit }),
    })
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<EntryViewer entry={original} onClose={onClose} />)
    expect(screen.getByRole('dialog', { name: 'View collection entry' })).toBeVisible()
    expect(screen.getByLabelText('Expression', { exact: true })).toHaveValue(original.text)
    expect(screen.getByLabelText('Contributor', { exact: true })).toHaveValue(original.contributor)
    expect(screen.getByLabelText('Source location', { exact: true })).toHaveValue(original.source_location)
    for (const field of screen.getAllByRole('textbox')) expect(field).toHaveAttribute('readonly')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Play recording: shared.wav')).toHaveAttribute('controls')
    expect(screen.getByRole('link', { name: 'Download audio' })).toHaveAttribute('href', '/api/dataset/fixture%2Fid%20with%20spaces/audio')
    expect(screen.queryByLabelText('Attach an audio file')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /save|record|upload|remove|delete|approve/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/Creator:|Historical name/)).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Expression', { exact: true }), 'Do not alter')
    expect(screen.getByLabelText('Expression', { exact: true })).toHaveValue(original.text)
    expect(fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Done' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('keeps legacy values and missing provenance honest instead of adding defaults', () => {
    render(<EntryViewer entry={entry({ entry_type: '', category: '', review_status: 'unreviewed', language: 'unspecified', contributor: '', audio_filename: '' })} onClose={vi.fn()} />)
    expect(screen.getByLabelText('Entry type', { exact: true })).toHaveValue('Not recorded (legacy)')
    expect(screen.getByLabelText('Category', { exact: true })).toHaveValue('Not recorded (legacy)')
    expect(screen.getByLabelText('Contributor', { exact: true })).toHaveValue('')
    expect(screen.getByText(/Review status: Unreviewed/)).toBeVisible()
    expect(screen.getByText(/No recording is available/)).toHaveTextContent('read-only')
    expect(screen.queryByRole('button', { name: /record|attach|upload/i })).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows recorded word classifications without making them editable or approving fieldwork', () => {
    render(<EntryViewer entry={entry({ entry_type: 'Word', lexical_category: 'SLANG' })} onClose={vi.fn()} />)
    expect(screen.getByLabelText('Lexical category', { exact: true })).toHaveValue('SLANG')
    expect(screen.getByLabelText('Lexical category', { exact: true })).toHaveAttribute('readonly')
    expect(screen.getByText(/Approval does not certify fieldwork/)).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })
})
