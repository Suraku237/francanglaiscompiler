import type { ComponentProps } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { EntryEditor } from '../../src/Collection'
import { entry, metadata } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'

function renderEditor(props: Partial<ComponentProps<typeof EntryEditor>> = {}) {
  const onClose = vi.fn()
  const onSaved = vi.fn()
  render(<EntryEditor metadata={metadata} onClose={onClose} onSaved={onSaved} {...props} />)
  return { user: userEvent.setup(), onClose, onSaved }
}

const approval = () => screen.getByRole('checkbox', { name: /I have reviewed the language/ })

describe('collection entry review', () => {
  it('rejects a whitespace-only expression without contacting the server', async () => {
    const { user } = renderEditor()
    await user.type(screen.getByRole('textbox', { name: /^Expression/ }), '   ')
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    expect(screen.getByRole('alert')).toHaveTextContent('It cannot contain only spaces.')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('never trusts imported approval and only creates a trimmed record after explicit save', async () => {
    const saved = entry({ text: 'Imported fixture', review_status: 'unreviewed' })
    vi.mocked(fetch).mockResolvedValue(jsonResponse(saved))
    const { user, onSaved } = renderEditor({
      initialDraft: { text: '  Imported fixture  ', review_status: 'approved', english_gloss: 'Draft meaning' },
    })
    expect(approval()).not.toBeChecked()
    expect(fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe('/api/dataset')
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.method).toBe('POST')
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toEqual({
      text: 'Imported fixture',
      entry_type: 'Sentence',
      language: 'unspecified',
      review_status: 'unreviewed',
      lexical_category: '',
      french_gloss: '',
      english_gloss: 'Draft meaning',
      category: 'Other',
      source_location: '',
      notes: '',
      contributor: '',
    })
    expect(onSaved).toHaveBeenCalledExactlyOnceWith(saved)
  })

  it.each([
    { label: /^Expression/, value: 'Revised expression', select: false },
    { label: /^French meaning/, value: 'Sens corrigé', select: false },
    { label: /^English meaning/, value: 'Revised meaning', select: false },
    { label: /^Context & notes/, value: 'Review uncertainty', select: false },
    { label: /^Language$/, value: 'pidgin', select: true },
    { label: /^Category$/, value: 'Other', select: true },
  ])('invalidates approval after changing $label', async ({ label, value, select }) => {
    const { user } = renderEditor({ entry: entry() })
    expect(approval()).toBeChecked()
    const field = screen.getByLabelText(label)
    if (select) await user.selectOptions(field, value)
    else {
      await user.clear(field)
      await user.type(field, value)
    }
    expect(approval()).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Save unreviewed' })).toBeEnabled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('patches changed editable fields only, preserving unchanged whitespace and provenance', async () => {
    const original = entry({
      id: 'fixture/id with spaces',
      text: '  Fixture expression  ',
      source_location: 'Existing fixture location',
      contributor: 'Fixture contributor',
      audio_filename: 'existing-fixture.wav',
    })
    const saved = { ...original, english_gloss: 'Updated meaning', review_status: 'unreviewed' as const }
    vi.mocked(fetch).mockResolvedValue(jsonResponse(saved))
    const { user, onSaved } = renderEditor({ entry: original })
    await user.clear(screen.getByLabelText(/^English meaning/))
    await user.type(screen.getByLabelText(/^English meaning/), 'Updated meaning')
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))

    expect(vi.mocked(fetch).mock.calls[0]?.[0]).toBe('/api/dataset/fixture%2Fid%20with%20spaces')
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.method).toBe('PATCH')
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toEqual({
      english_gloss: 'Updated meaning', review_status: 'unreviewed',
    })
    expect(onSaved).toHaveBeenCalledExactlyOnceWith(saved)
  })

  it('submits approval as a separate human decision without fabricating missing metadata', async () => {
    const original = entry({ review_status: 'unreviewed', category: 'Legacy topic', entry_type: '' })
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ...original, review_status: 'approved' }))
    const { user } = renderEditor({ entry: original })
    expect(screen.getByLabelText(/^Category$/)).toHaveValue('Legacy topic')
    expect(screen.getByLabelText(/^Entry type$/)).toHaveValue('')
    await user.click(approval())
    await user.click(screen.getByRole('button', { name: 'Save approved entry' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toEqual({ review_status: 'approved' })
  })

  it('closes an unchanged entry without a mutation', async () => {
    const { user, onClose, onSaved } = renderEditor({ entry: entry() })
    await user.click(screen.getByRole('button', { name: 'Save approved entry' }))
    expect(onClose).toHaveBeenCalledOnce()
    expect(onSaved).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('clears a word-only lexical category when the entry becomes a phrase', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(entry({ entry_type: 'Phrase', review_status: 'unreviewed' })))
    const { user } = renderEditor({ entry: entry({ entry_type: 'Word', lexical_category: 'NOUN' }) })
    expect(screen.queryByLabelText(/^Lexical category/)).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText(/^Entry type$/), 'Phrase')
    expect(screen.queryByLabelText(/^Lexical category/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toEqual({
      entry_type: 'Phrase', lexical_category: '', review_status: 'unreviewed',
    })
  })

  it('locks edits and dismissal while saving, preventing duplicate mutation requests', async () => {
    const saving = deferred<Response>()
    vi.mocked(fetch).mockReturnValue(saving.promise)
    const { user, onClose, onSaved } = renderEditor({ initialDraft: { text: 'Fixture' } })
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    expect(screen.getByRole('textbox', { name: /^Expression/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Close dialog' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: /Saving/ }))
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    expect(onClose).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledOnce()

    const saved = entry({ text: 'Fixture', review_status: 'unreviewed' })
    await act(async () => saving.resolve(jsonResponse(saved)))
    expect(onSaved).toHaveBeenCalledExactlyOnceWith(saved)
  })

  it('keeps the draft on a rejected save and clears the error when it is corrected', async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ detail: 'Review the language before saving.' }, 422))
      .mockResolvedValueOnce(jsonResponse(entry({ review_status: 'unreviewed' })))
    const { user, onClose, onSaved } = renderEditor({ initialDraft: { text: 'Fixture' } })
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Review the language before saving.')
    expect(screen.getByLabelText(/^Expression/)).toHaveValue('Fixture')
    expect(onClose).not.toHaveBeenCalled()
    expect(onSaved).not.toHaveBeenCalled()
    await user.selectOptions(screen.getByLabelText(/^Language$/), 'pidgin')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    expect(onSaved).toHaveBeenCalledOnce()
  })
})
