import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Imports } from '../../src/Imports'
import { IMPORT_ACCEPT, MAX_IMPORT_BYTES } from '../../src/importTypes'
import { entry, importPreview, metadata } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'

function renderImports() {
  vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(metadata))
  const props = { active: true, onUseText: vi.fn(), onOpenCollection: vi.fn() }
  const view = render(<Imports {...props} />)
  return { ...view, props, user: userEvent.setup({ applyAccept: false }) }
}

function formBody(index = 1): FormData {
  const body = vi.mocked(fetch).mock.calls[index]?.[1]?.body
  if (!(body instanceof FormData)) throw new Error('Expected a multipart import request')
  return body
}

const fileInput = () => screen.getByLabelText('Text document')
const previewButton = () => screen.getByRole('button', { name: 'Preview source text' })
const fixtureFile = () => new File(['Synthetic fixture content.'], 'fixture.txt', { type: 'text/plain' })

describe('local document review and manual compiler handoff', () => {
  it('previews exactly one file without consent fields and hands off raw spacing without computing', async () => {
    const { user, props } = renderImports()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(importPreview()))
    await user.upload(fileInput(), fixtureFile())
    expect(fileInput()).toHaveAttribute('accept', IMPORT_ACCEPT)
    expect(fileInput()).not.toHaveAttribute('multiple')
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
    await user.click(previewButton())
    expect([...formBody().keys()]).toEqual(['file'])
    expect(formBody().get('file')).toBeInstanceOf(File)
    expect(await screen.findByText(/fixture.txt · Extracted locally/)).toBeInTheDocument()
    expect(screen.getByText('Synthetic fixture; review before use.')).toBeInTheDocument()

    const raw = '  Mbom,\tTu  es where?\n\n'
    await user.clear(screen.getByLabelText('Review and correct this passage'))
    await user.click(screen.getByLabelText('Review and correct this passage'))
    await user.paste(raw)
    await user.click(screen.getByRole('button', { name: 'Open in compiler' }))
    expect(props.onUseText).toHaveBeenCalledExactlyOnceWith(raw)
    expect(screen.queryByRole('button', { name: /assistant|translate|suggest|AI/i })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it.each([
    { name: 'empty', size: 0, message: 'This file is empty.' },
    { name: 'oversized', size: MAX_IMPORT_BYTES + 1, message: 'This file exceeds 12 MB.' },
  ])('rejects an $name file before a preview request', async ({ size, message }) => {
    const { user } = renderImports()
    const file = fixtureFile()
    Object.defineProperty(file, 'size', { value: size })
    await user.upload(fileInput(), file)
    expect(previewButton()).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it.each(['fixture.png', 'fixture.webm', 'fixture.exe'])('rejects %s without uploading or transcribing', async (name) => {
    const { user, props } = renderImports()
    await user.upload(fileInput(), new File(['raw fixture'], name))
    expect(previewButton()).toBeDisabled()
    expect(screen.getByRole('alert')).toHaveTextContent('manual text transcript')
    expect(screen.queryByRole('button', { name: 'Record audio' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Open Collection for raw recordings' }))
    expect(props.onOpenCollection).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('surfaces the scanned-PDF manual-transcript error, then displays mixed-page extraction warnings', async () => {
    const { user } = renderImports()
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ detail: 'This PDF has no text layer. Supply a manual transcript; OCR is not available.' }, 422))
      .mockResolvedValueOnce(jsonResponse(importPreview({
        filename: 'mixed.pdf', format: 'pdf', warnings: ['Page 2 has no text layer and was omitted. Transcribe it manually.'],
      })))
    await user.upload(fileInput(), new File(['fixture only'], 'scan.pdf', { type: 'application/pdf' }))
    await user.click(previewButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('Supply a manual transcript')
    expect(screen.queryByLabelText('Review and correct this passage')).not.toBeInTheDocument()
    await user.upload(fileInput(), new File(['fixture only'], 'mixed.pdf', { type: 'application/pdf' }))
    await user.click(previewButton())
    expect(await screen.findByText(/Page 2 has no text layer/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(formBody(2).has('allow_cloud_processing')).toBe(false)
  })

  it('preserves imported annotation fields but never imported approval or authenticity', async () => {
    const { user } = renderImports()
    const draft = {
      text: '  Imported fixture expression  ', entry_type: 'Word' as const, language: 'pidgin' as const,
      french_gloss: 'Sens source', english_gloss: 'Source meaning', lexical_category: 'NOUN',
      category: 'Campus Life', source_location: 'Original transcript line 7', contributor: 'Alias from source',
      notes: 'Original uncertainty and permission notes.', review_status: 'unreviewed' as const,
    }
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(importPreview({ drafts: [{ ...draft, review_status: 'approved' } as unknown as typeof draft] })))
    await user.upload(fileInput(), fixtureFile())
    await user.click(previewButton())
    await user.click(await screen.findByRole('button', { name: 'Review and save candidate' }))
    expect(screen.getByRole('dialog', { name: 'Add collection entry' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^Expression/)).toHaveValue(draft.text)
    expect(screen.getByLabelText(/^Source location/)).toHaveValue(draft.source_location)
    expect(screen.getByLabelText(/^Contributor/)).toHaveValue(draft.contributor)
    expect(screen.getByLabelText(/^Context & notes/)).toHaveValue(draft.notes)
    expect(screen.getByLabelText(/^Category$/)).toHaveValue(draft.category)
    expect(screen.getByLabelText(/^Lexical category/)).toHaveValue('NOUN')
    expect(screen.getByRole('checkbox', { name: /I have reviewed/ })).not.toBeChecked()
    expect(fetch).toHaveBeenCalledTimes(2)
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(entry({ ...draft })))
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    expect(await screen.findByText(/This entry remains unreviewed/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Saved - manage in Collection' })).toBeDisabled()
    expect(requestBody(vi.mocked(fetch).mock.calls[2])).toEqual(draft)
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('/coursework/project'))).toBe(false)
  })

  it('keeps absent provenance unknown and changes passages without writing to the source', async () => {
    const { user } = renderImports()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(importPreview({ drafts: [] })))
    await user.upload(fileInput(), fixtureFile())
    await user.click(previewButton())
    await user.type(await screen.findByLabelText('Review and correct this passage'), ' corrected')
    await user.selectOptions(screen.getByLabelText('Choose a passage'), '1')
    expect(screen.getByLabelText('Review and correct this passage')).toHaveValue('Second fixture passage.')
    await user.click(screen.getByRole('button', { name: 'Review passage as an entry' }))
    expect(screen.getByLabelText(/^Source location/)).toHaveValue('')
    expect(screen.getByLabelText(/^Contributor/)).toHaveValue('')
    expect(screen.getByLabelText(/^Language$/)).toHaveValue('unspecified')
    expect(screen.getByLabelText(/^Context & notes/)).toHaveValue('Source file: fixture.txt. Locally extracted text; verify the manual transcription, source, context and permissions. Importing does not establish authenticity.')
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('cancels a preview on navigation and ignores its late response', async () => {
    const { user, props, rerender } = renderImports()
    const old = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(old.promise)
    await user.upload(fileInput(), fixtureFile())
    await user.click(previewButton())
    rerender(<Imports {...props} active={false} />)
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.signal?.aborted).toBe(true)
    await act(async () => old.resolve(jsonResponse(importPreview())))
    expect(screen.queryByRole('heading', { name: 'Content preview' })).not.toBeInTheDocument()
  })
})
