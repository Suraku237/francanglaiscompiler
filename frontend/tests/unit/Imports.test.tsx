import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Imports } from '../../src/Imports'
import { MAX_IMPORT_BYTES } from '../../src/importTypes'
import { entry, importPreview, importSuggestions, metadata } from '../fixtures'
import { deferred, jsonResponse, requestBody } from '../helpers'

function renderImports(aiAvailable = true) {
  vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(metadata))
  const props = { active: true, aiAvailable, onUseText: vi.fn(), onAskAI: vi.fn(), onOpenCollection: vi.fn() }
  const view = render(<Imports {...props} />)
  return { ...view, props, user: userEvent.setup() }
}

function formBody(index = 1): FormData {
  const body = vi.mocked(fetch).mock.calls[index]?.[1]?.body
  if (!(body instanceof FormData)) throw new Error('Expected a multipart import request')
  return body
}

const fileInput = () => screen.getByLabelText('Document, image, audio or video')
const previewButton = () => screen.getByRole('button', { name: 'Preview source text' })
const consent = () => screen.getByRole('checkbox', { name: /I consent to sending this file to Gemini/ })
const fixtureFile = () => new File(['Synthetic fixture content.'], 'fixture.txt', { type: 'text/plain' })

describe('import consent, review and handoff', () => {
  it('previews local text without cloud consent and hands off corrected drafts without submitting them', async () => {
    const { user, props } = renderImports(false)
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(importPreview()))
    await user.upload(fileInput(), fixtureFile())
    expect(consent()).toBeDisabled()
    expect(consent()).not.toBeChecked()
    expect(fetch).toHaveBeenCalledTimes(1)
    await user.click(previewButton())
    expect(formBody().get('allow_cloud_processing')).toBe('false')
    expect(formBody().get('file')).toBeInstanceOf(File)
    expect(await screen.findByText(/fixture.txt · Extracted locally/)).toBeInTheDocument()
    expect(screen.getByText('Synthetic fixture; review before use.')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Review and correct this passage'))
    await user.type(screen.getByLabelText('Review and correct this passage'), 'Corrected fixture')
    await user.click(screen.getByRole('button', { name: 'Open in translator' }))
    await user.click(screen.getByRole('button', { name: 'Open in assistant' }))
    expect(props.onUseText).toHaveBeenCalledExactlyOnceWith('Corrected fixture')
    expect(props.onAskAI).toHaveBeenCalledExactlyOnceWith('Corrected fixture')
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('surfaces media-consent errors and sends consent only after an explicit retry', async () => {
    const { user } = renderImports()
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ detail: 'Cloud consent is required for this media file.' }, 400))
      .mockResolvedValueOnce(jsonResponse(importPreview({ filename: 'fixture.png', format: 'png', method: 'gemini' })))
    await user.upload(fileInput(), new File(['Synthetic media fixture, never decoded.'], 'fixture.png', { type: 'image/png' }))
    await user.click(previewButton())
    expect(formBody().get('allow_cloud_processing')).toBe('false')
    expect(await screen.findByRole('alert')).toHaveTextContent('Cloud consent is required')
    expect(screen.queryByLabelText('Review and correct this passage')).not.toBeInTheDocument()

    await user.click(consent())
    expect(fetch).toHaveBeenCalledTimes(2)
    await user.click(previewButton())
    expect(formBody(2).get('allow_cloud_processing')).toBe('true')
    expect(await screen.findByText(/Unreviewed AI transcript/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each([
    { name: 'empty', size: 0, message: 'This file is empty.' },
    { name: 'oversized', size: MAX_IMPORT_BYTES + 1, message: 'This file exceeds 12 MB.' },
  ])('rejects an $name file before a preview request', async ({ size, message }) => {
    const { user } = renderImports()
    const file = fixtureFile()
    Object.defineProperty(file, 'size', { value: size })
    await user.upload(fileInput(), file)
    await user.click(previewButton())
    expect(screen.getByRole('alert')).toHaveTextContent(message)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('opens unreviewed candidates with honest provenance and saves only after explicit review', async () => {
    const { user } = renderImports()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(importPreview()))
    await user.upload(fileInput(), fixtureFile())
    await user.click(previewButton())
    await user.click(await screen.findByRole('button', { name: 'Review and save candidate' }))
    expect(screen.getByRole('dialog', { name: 'Add an expression to learn' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^Expression/)).toHaveValue('Imported fixture expression')
    expect(screen.getByLabelText(/^Language$/)).toHaveValue('pidgin')
    expect(screen.getByLabelText(/^Context & notes/)).toHaveValue(
      'Source file: fixture.txt. Locally extracted text, not proof of fieldwork. Imported alignment; human review required.',
    )
    expect(screen.getByLabelText(/^Source location/)).toHaveValue('')
    expect(screen.getByLabelText(/^Contributor/)).toHaveValue('')
    expect(screen.getByRole('checkbox', { name: /I have reviewed/ })).not.toBeChecked()
    expect(fetch).toHaveBeenCalledTimes(2)

    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(entry({ review_status: 'unreviewed' })))
    await user.click(screen.getByRole('button', { name: 'Save unreviewed' }))
    expect(await screen.findByText(/It remains unreviewed and is not trusted translation evidence/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Saved - manage in Collection' })).toBeDisabled()
    expect(requestBody(vi.mocked(fetch).mock.calls[2])).toEqual(expect.objectContaining({
      review_status: 'unreviewed', source_location: '', contributor: '',
    }))
  })

  it('cancels candidate generation on correction and ignores late suggestions', async () => {
    const { user } = renderImports()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(importPreview()))
    await user.upload(fileInput(), fixtureFile())
    await user.click(previewButton())
    const oldSuggestions = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(oldSuggestions.promise)
    await user.click(await screen.findByRole('button', { name: 'Ask AI for vocabulary candidates' }))
    expect(requestBody(vi.mocked(fetch).mock.calls[2])).toEqual({
      text: 'First fixture passage.', language: 'francanglais',
    })
    await user.type(screen.getByLabelText('Review and correct this passage'), ' corrected')
    expect(vi.mocked(fetch).mock.calls[2]?.[1]?.signal?.aborted).toBe(true)
    await act(async () => oldSuggestions.resolve(jsonResponse(importSuggestions())))
    expect(screen.queryByText('AI fixture candidate')).not.toBeInTheDocument()
    expect(screen.getByText('Imported fixture expression')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask AI for vocabulary candidates' })).toBeEnabled()
  })

  it('discards passage corrections and generated candidates when choosing a different passage', async () => {
    const { user } = renderImports()
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(importPreview()))
    await user.upload(fileInput(), fixtureFile())
    await user.click(previewButton())
    await user.type(await screen.findByLabelText('Review and correct this passage'), ' corrected')
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(importSuggestions()))
    await user.click(screen.getByRole('button', { name: 'Ask AI for vocabulary candidates' }))
    expect(await screen.findByText('AI fixture candidate')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Choose a passage'), '1')
    expect(screen.getByLabelText('Review and correct this passage')).toHaveValue('Second fixture passage.')
    expect(screen.queryByText('AI fixture candidate')).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('cancels previews on navigation, retaining the selected file but not a stale preview', async () => {
    const { user, rerender, props } = renderImports()
    const oldPreview = deferred<Response>()
    vi.mocked(fetch).mockReturnValueOnce(oldPreview.promise)
    await user.upload(fileInput(), fixtureFile())
    await user.click(previewButton())
    rerender(<Imports {...props} active={false} />)
    expect(vi.mocked(fetch).mock.calls[1]?.[1]?.signal?.aborted).toBe(true)
    await act(async () => oldPreview.resolve(jsonResponse(importPreview())))
    expect(screen.queryByLabelText('Review and correct this passage')).not.toBeInTheDocument()
    expect(previewButton()).toBeEnabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
