import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CourseworkScreenshots } from '../../src/CourseworkEvidence'
import type { Screenshot } from '../../src/courseworkTypes'
import { jsonResponse, requestBody } from '../helpers'

afterEach(() => vi.restoreAllMocks())

function deferredFileReads() {
  const readers: FileReader[] = []
  vi.spyOn(FileReader.prototype, 'readAsDataURL').mockImplementation(function (this: FileReader) {
    readers.push(this)
  })
  return (index: number, dataUrl: string) => {
    const reader = readers[index]
    if (!reader) throw new Error(`No pending fixture read at index ${index}`)
    Object.defineProperty(reader, 'result', { configurable: true, value: dataUrl })
    reader.dispatchEvent(new ProgressEvent('load'))
  }
}

describe('coursework screenshot captions', () => {
  it('keeps a caption edited during an image read and uploads that exact caption', async () => {
    const finishRead = deferredFileReads()
    const user = userEvent.setup()
    const dataUrl = 'data:image/png;base64,ZmFrZS1maXh0dXJl'
    const caption = 'Synthetic screenshot fixture'
    let images: Screenshot[] = []
    render(<CourseworkScreenshots screenshots={images} busy={false} onBusyChange={vi.fn()} onChanged={(update) => { images = update(images) }} />)
    await user.upload(screen.getByLabelText('Choose PNG or JPEG · max 2 MB'), new File(['fixture'], 'image.png', { type: 'image/png' }))
    await user.clear(screen.getByLabelText('Screenshot caption'))
    await user.type(screen.getByLabelText('Screenshot caption'), caption)
    expect(screen.getByRole('button', { name: 'Save screenshot to project' })).toBeDisabled()
    act(() => finishRead(0, dataUrl))
    expect(screen.getByLabelText('Screenshot caption')).toHaveValue(caption)
    expect(screen.getByRole('button', { name: 'Save screenshot to project' })).toBeEnabled()

    const saved = { id: 'fixture-image', name: caption, url: '/api/coursework/screenshots/fixture-image' }
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(saved))
    await user.click(screen.getByRole('button', { name: 'Save screenshot to project' }))
    expect(await screen.findByText(/Screenshot saved privately in this project/)).toBeInTheDocument()
    expect(requestBody(vi.mocked(fetch).mock.calls[0])).toEqual({ name: caption, data_url: dataUrl })
    expect(images).toEqual([saved])
  })

  it('ignores an older image read without overwriting the latest caption or enabling an early upload', async () => {
    const finishRead = deferredFileReads()
    const user = userEvent.setup()
    render(<CourseworkScreenshots screenshots={[]} busy={false} onBusyChange={vi.fn()} onChanged={vi.fn()} />)
    const input = screen.getByLabelText('Choose PNG or JPEG · max 2 MB')
    await user.upload(input, new File(['older fixture'], 'older.png', { type: 'image/png' }))
    await user.upload(input, new File(['newer fixture'], 'newer.png', { type: 'image/png' }))
    await user.clear(screen.getByLabelText('Screenshot caption'))
    await user.type(screen.getByLabelText('Screenshot caption'), 'My latest caption')
    act(() => finishRead(0, 'data:image/png;base64,b2xk'))
    expect(screen.getByRole('button', { name: 'Save screenshot to project' })).toBeDisabled()
    expect(screen.getByLabelText('Screenshot caption')).toHaveValue('My latest caption')
    act(() => finishRead(1, 'data:image/png;base64,bmV3'))
    expect(screen.getByLabelText('Screenshot caption')).toHaveValue('My latest caption')
    expect(screen.getByAltText('Selected screenshot: My latest caption')).toHaveAttribute('src', 'data:image/png;base64,bmV3')
    expect(screen.getByRole('button', { name: 'Save screenshot to project' })).toBeEnabled()
    expect(fetch).not.toHaveBeenCalled()
  })
})
