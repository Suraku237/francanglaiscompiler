import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useRequest } from '../../src/useRequest'
import { deferred } from '../helpers'

describe('useRequest', () => {
  it('allows one in-flight operation and completes only the submitted callback', async () => {
    const work = deferred<string>()
    const first = vi.fn(() => work.promise)
    const duplicate = vi.fn(async () => 'duplicate')
    const onSuccess = vi.fn()
    const { result } = renderHook(useRequest)

    act(() => {
      void result.current.run(first, onSuccess)
      void result.current.run(duplicate, onSuccess)
    })
    expect(result.current.pending).toBe(true)
    expect(first).toHaveBeenCalledOnce()
    expect(duplicate).not.toHaveBeenCalled()

    await act(async () => work.resolve('result'))
    expect(onSuccess).toHaveBeenCalledExactlyOnceWith('result')
    expect(result.current.pending).toBe(false)
    expect(result.current.error).toBe('')
  })

  it('cancels immediately and ignores a late success even if the work ignores its signal', async () => {
    const work = deferred<string>()
    const onSuccess = vi.fn()
    let signal: AbortSignal | undefined
    const { result } = renderHook(useRequest)

    act(() => {
      void result.current.run((current) => {
        signal = current
        return work.promise
      }, onSuccess)
    })
    act(() => result.current.cancel())
    expect(signal?.aborted).toBe(true)
    expect(result.current.pending).toBe(false)

    await act(async () => work.resolve('stale'))
    expect(onSuccess).not.toHaveBeenCalled()
    expect(result.current.error).toBe('')
  })

  it('does not let a cancelled response finish or overwrite a newer in-flight request', async () => {
    const oldWork = deferred<string>()
    const newWork = deferred<string>()
    const oldSuccess = vi.fn()
    const newSuccess = vi.fn()
    const { result } = renderHook(useRequest)

    act(() => { void result.current.run(() => oldWork.promise, oldSuccess) })
    act(() => {
      result.current.cancel()
      void result.current.run(() => newWork.promise, newSuccess)
    })
    await act(async () => oldWork.resolve('old'))
    expect(result.current.pending).toBe(true)
    expect(oldSuccess).not.toHaveBeenCalled()
    expect(newSuccess).not.toHaveBeenCalled()

    await act(async () => newWork.resolve('new'))
    expect(newSuccess).toHaveBeenCalledExactlyOnceWith('new')
    expect(result.current.pending).toBe(false)
  })

  it('ignores a late rejection without erasing a newer request error', async () => {
    const oldWork = deferred<string>()
    const { result } = renderHook(useRequest)
    act(() => { void result.current.run(() => oldWork.promise, vi.fn()) })
    act(() => result.current.cancel())

    await act(async () => {
      await result.current.run(async () => { throw new Error('Current failure') }, vi.fn())
    })
    await act(async () => oldWork.reject(new Error('Stale failure')))
    expect(result.current.error).toBe('Current failure')
    expect(result.current.pending).toBe(false)
  })

  it('aborts on unmount and never delivers a late result', async () => {
    const work = deferred<string>()
    const onSuccess = vi.fn()
    let signal: AbortSignal | undefined
    const { result, unmount } = renderHook(useRequest)
    act(() => {
      void result.current.run((current) => {
        signal = current
        return work.promise
      }, onSuccess)
    })
    unmount()
    expect(signal?.aborted).toBe(true)
    await act(async () => work.resolve('late'))
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('keeps AbortError silent and lets callers explicitly clear a real error', async () => {
    const { result } = renderHook(useRequest)
    await act(async () => {
      await result.current.run(async () => { throw new DOMException('Cancelled', 'AbortError') }, vi.fn())
    })
    expect(result.current.error).toBe('')
    await act(async () => {
      await result.current.run(async () => { throw new Error('Try again') }, vi.fn())
    })
    expect(result.current.error).toBe('Try again')
    act(() => result.current.clearError())
    expect(result.current.error).toBe('')
  })

  it('clears previous errors when retrying and reports unknown failures safely', async () => {
    const retry = deferred<string>()
    const { result } = renderHook(useRequest)
    await act(async () => {
      await result.current.run(() => Promise.reject(null), vi.fn())
    })
    expect(result.current.error).toBe('Something went wrong. Please try again.')
    act(() => { void result.current.run(() => retry.promise, vi.fn()) })
    expect(result.current.error).toBe('')
    expect(result.current.pending).toBe(true)
    await act(async () => retry.resolve('recovered'))
    expect(result.current.pending).toBe(false)
  })
})
