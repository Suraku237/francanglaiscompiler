import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CourseworkExport } from '../../src/CourseworkEvidence'
import { configureSession, selectProject } from '../../src/api'
import { deferred, jsonResponse } from '../helpers'

function mockDownloads() {
  const create = vi.fn(() => 'blob:fixture-coursework')
  const revoke = vi.fn()
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = create
    static revokeObjectURL = revoke
  })
  const links: HTMLAnchorElement[] = []
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    links.push(this)
  })
  return { create, revoke, links }
}

const downloadButton = () => screen.getByRole('button', { name: 'Download coursework draft (.zip)' })
const zipResponse = () => new Response(new Uint8Array([0x50, 0x4b, 0x05, 0x06, ...new Array<number>(18).fill(0)]), {
  headers: { 'Content-Type': 'application/zip' },
})
afterEach(() => configureSession(null))

describe('coursework export', () => {
  it('downloads only the authenticated selected project and not the default project', async () => {
    configureSession('test-csrf')
    selectProject('project with spaces')
    mockDownloads()
    vi.mocked(fetch).mockResolvedValueOnce(zipResponse())
    render(<CourseworkExport active dirty={false} busy={false} />)
    await userEvent.setup().click(downloadButton())
    expect(await screen.findByText(/Draft download started/)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/coursework/export?project=project%20with%20spaces', expect.objectContaining({
      cache: 'no-store', credentials: 'same-origin',
    }))
  })

  it('expires the account UI on an unauthorized private export without downloading', async () => {
    const expired = vi.fn()
    window.addEventListener('mboa:session-expired', expired)
    const downloads = mockDownloads()
    try {
      vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: 'Sign in to export this project.' }, 401))
      render(<CourseworkExport active dirty={false} busy={false} />)
      await userEvent.setup().click(downloadButton())
      expect(await screen.findByRole('alert')).toHaveTextContent('Sign in to export')
      expect(expired).toHaveBeenCalledOnce()
      expect(downloads.create).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener('mboa:session-expired', expired)
    }
  })

  it.each([
    { dirty: true, busy: false },
    { dirty: false, busy: true },
  ])('does not request an export when dirty=$dirty or busy=$busy', async (props) => {
    const user = userEvent.setup()
    render(<CourseworkExport active {...props} />)
    expect(downloadButton()).toBeDisabled()
    await user.click(downloadButton())
    expect(fetch).not.toHaveBeenCalled()
  })

  it('downloads a validated ZIP with no editor payload and releases the object URL on unmount', async () => {
    const user = userEvent.setup()
    const downloads = mockDownloads()
    vi.mocked(fetch).mockResolvedValue(zipResponse())
    const { unmount } = render(<CourseworkExport active dirty={false} busy={false} />)
    await user.click(downloadButton())

    expect(await screen.findByText(/Draft download started/)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/coursework/export', expect.objectContaining({
      signal: expect.any(AbortSignal), cache: 'no-store',
    }))
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.body).toBeUndefined()
    expect(downloads.create).toHaveBeenCalledOnce()
    expect(downloads.links).toHaveLength(1)
    expect(downloads.links[0]?.download).toBe('francanglais-coursework.zip')
    expect(downloads.links[0]).not.toBeInTheDocument()
    unmount()
    expect(downloads.revoke).toHaveBeenCalledExactlyOnceWith('blob:fixture-coursework')
  })

  it.each([
    { name: 'HTTP failure', response: () => jsonResponse({ detail: 'Save the grammar first.' }, 409), message: 'Save the grammar first.' },
    { name: 'wrong content type', response: () => jsonResponse({ ok: true }), message: 'The server did not return a ZIP file.' },
    { name: 'empty ZIP', response: () => new Response('', { headers: { 'Content-Type': 'application/zip' } }), message: 'The export was empty.' },
  ])('refuses a $name instead of starting a misleading download', async ({ response, message }) => {
    const user = userEvent.setup()
    const downloads = mockDownloads()
    vi.mocked(fetch).mockResolvedValue(response())
    render(<CourseworkExport active dirty={false} busy={false} />)
    await user.click(downloadButton())
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(downloads.create).not.toHaveBeenCalled()
    expect(downloadButton()).toBeEnabled()
  })

  it('reports a connection failure and supports retrying explicitly', async () => {
    const user = userEvent.setup()
    mockDownloads()
    vi.mocked(fetch)
      .mockRejectedValueOnce(new TypeError('Network interrupted'))
      .mockResolvedValueOnce(zipResponse())
    render(<CourseworkExport active dirty={false} busy={false} />)
    await user.click(downloadButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot download from the application server.')
    await user.click(downloadButton())
    expect(await screen.findByText(/Draft download started/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('cancels an in-flight download on a new edit and discards a late ZIP response', async () => {
    const user = userEvent.setup()
    const downloads = mockDownloads()
    const oldDownload = deferred<Response>()
    vi.mocked(fetch).mockReturnValue(oldDownload.promise)
    const { rerender } = render(<CourseworkExport active dirty={false} busy={false} />)
    await user.click(downloadButton())
    rerender(<CourseworkExport active dirty busy={false} />)
    expect(vi.mocked(fetch).mock.calls[0]?.[1]?.signal?.aborted).toBe(true)
    await act(async () => oldDownload.resolve(zipResponse()))
    expect(downloads.create).not.toHaveBeenCalled()
    expect(screen.queryByText(/Draft download started/)).not.toBeInTheDocument()
    expect(downloadButton()).toBeDisabled()
  })
})
