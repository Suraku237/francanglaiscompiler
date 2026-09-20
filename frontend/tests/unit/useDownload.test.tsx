import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDownload } from '../../src/useDownload'

afterEach(() => vi.restoreAllMocks())

describe('local business exports', () => {
  it('starts an explicit download and releases the temporary URL on unmount', () => {
    const createObjectURL = vi.fn(() => 'blob:business-export')
    const revokeObjectURL = vi.fn()
    const BaseURL = URL
    vi.stubGlobal('URL', class extends BaseURL {
      static createObjectURL = createObjectURL
      static revokeObjectURL = revokeObjectURL
    })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const { result, unmount } = renderHook(useDownload)
    const blob = new Blob(['{"entries":[]}'], { type: 'application/json' })
    act(() => expect(result.current.download(blob, 'terms.json')).toBe(true))
    expect(createObjectURL).toHaveBeenCalledExactlyOnceWith(blob)
    expect(click).toHaveBeenCalledOnce()
    expect(fetch).not.toHaveBeenCalled()
    expect(document.querySelector('a[download]')).toBeNull()
    unmount()
    expect(revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:business-export')
  })

  it('shows a download failure without claiming success', () => {
    const BaseURL = URL
    vi.stubGlobal('URL', class extends BaseURL {
      static createObjectURL = () => { throw new Error('Storage blocked') }
    })
    const { result } = renderHook(useDownload)
    act(() => expect(result.current.download(new Blob(['data']), 'terms.json')).toBe(false))
    expect(result.current.error).toContain('download could not start')
    expect(document.querySelector('a[download]')).toBeNull()
  })
})
