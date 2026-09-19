import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { claimAudioFocus } from '../../src/audioFocus'
import { MAX_IMPORT_BYTES } from '../../src/importTypes'
import { useAudioRecorder } from '../../src/useAudioRecorder'
import { audioFixtures, currentFixtureRecorder, FixtureRecorder } from '../audioFixtures'
import { deferred } from '../helpers'

describe('local browser recording lifecycle', () => {
  it('records only after an explicit start and finishes a local file without a request', async () => {
    const { getUserMedia, track } = audioFixtures()
    const onRecorded = vi.fn()
    const { result } = renderHook(() => useAudioRecorder(true, onRecorded))
    expect(getUserMedia).not.toHaveBeenCalled()
    await act(() => result.current.start())
    expect(getUserMedia).toHaveBeenCalledExactlyOnceWith({ audio: true, video: false })
    expect(result.current.phase).toBe('recording')
    expect(onRecorded).not.toHaveBeenCalled()
    await act(async () => result.current.stop())
    expect(result.current.phase).toBe('idle')
    expect(track.stop).toHaveBeenCalledOnce()
    expect(onRecorded).toHaveBeenCalledOnce()
    const file: unknown = onRecorded.mock.calls[0]?.[0]
    expect(file).toBeInstanceOf(File)
    if (!(file instanceof File)) throw new Error('Expected a captured audio file')
    expect(file.name).toMatch(/\.webm$/)
    expect(file.size).toBeGreaterThan(0)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('rejects duplicate starts while microphone permission is pending', async () => {
    const { getUserMedia, stream } = audioFixtures()
    const permission = deferred<typeof stream>()
    getUserMedia.mockReturnValue(permission.promise)
    const { result } = renderHook(() => useAudioRecorder(true, vi.fn()))
    act(() => {
      void result.current.start()
      void result.current.start()
    })
    expect(getUserMedia).toHaveBeenCalledOnce()
    await act(async () => permission.resolve(stream))
  })

  it('releases a late permission grant after cancellation and never starts recording', async () => {
    const { getUserMedia, stream, track } = audioFixtures()
    const permission = deferred<typeof stream>()
    getUserMedia.mockReturnValue(permission.promise)
    const onRecorded = vi.fn()
    const { result } = renderHook(() => useAudioRecorder(true, onRecorded))
    act(() => { void result.current.start() })
    expect(result.current.phase).toBe('requesting')
    act(() => result.current.cancel())
    await act(async () => permission.resolve(stream))
    expect(track.stop).toHaveBeenCalledOnce()
    expect(FixtureRecorder.instances).toHaveLength(0)
    expect(onRecorded).not.toHaveBeenCalled()
    expect(result.current.phase).toBe('idle')
  })

  it.each([
    ['NotAllowedError', 'permission was denied'],
    ['NotFoundError', 'No microphone was found'],
    ['NotReadableError', 'unavailable or in use'],
  ])('shows an actionable %s error and allows retry', async (name, message) => {
    const { getUserMedia, stream } = audioFixtures()
    getUserMedia.mockRejectedValueOnce(new DOMException('Fixture failure', name)).mockResolvedValue(stream)
    const { result } = renderHook(() => useAudioRecorder(true, vi.fn()))
    await act(() => result.current.start())
    expect(result.current.error).toContain(message)
    expect(result.current.phase).toBe('idle')
    await act(() => result.current.start())
    expect(result.current.phase).toBe('recording')
    expect(result.current.error).toBe('')
  })

  it('releases a failed recorder start without producing a false attachment', async () => {
    const { track } = audioFixtures()
    FixtureRecorder.failStart = true
    const onRecorded = vi.fn()
    const { result } = renderHook(() => useAudioRecorder(true, onRecorded))
    await act(() => result.current.start())
    expect(result.current.phase).toBe('idle')
    expect(result.current.error).toContain('unavailable')
    expect(track.stop).toHaveBeenCalledOnce()
    expect(onRecorded).not.toHaveBeenCalled()
  })

  it('stops and keeps the clip when leaving its workspace', async () => {
    const { track } = audioFixtures()
    const onRecorded = vi.fn()
    const { result, rerender } = renderHook(({ active }) => useAudioRecorder(active, onRecorded), { initialProps: { active: true } })
    await act(() => result.current.start())
    await act(async () => rerender({ active: false }))
    expect(track.stop).toHaveBeenCalledOnce()
    expect(onRecorded).toHaveBeenCalledOnce()
    expect(result.current.phase).toBe('idle')
  })

  it('releases all resources on unmount and ignores a late stop event', async () => {
    const { track } = audioFixtures()
    const onRecorded = vi.fn()
    const { result, unmount } = renderHook(() => useAudioRecorder(true, onRecorded))
    await act(() => result.current.start())
    unmount()
    await act(async () => {})
    expect(track.stop).toHaveBeenCalledOnce()
    expect(onRecorded).not.toHaveBeenCalled()
  })

  it('stops oversized capture without replacing the previous attachment', async () => {
    const { track } = audioFixtures()
    const onRecorded = vi.fn()
    const { result } = renderHook(() => useAudioRecorder(true, onRecorded))
    await act(() => result.current.start())
    const oversized = new Blob(['synthetic'])
    Object.defineProperty(oversized, 'size', { value: MAX_IMPORT_BYTES + 1 })
    await act(async () => currentFixtureRecorder().ondataavailable?.({ data: oversized }))
    expect(result.current.error).toContain('exceeded 12 MB')
    expect(track.stop).toHaveBeenCalledOnce()
    expect(onRecorded).not.toHaveBeenCalled()
    expect(result.current.phase).toBe('idle')
  })

  it('makes microphone disconnection explicit while retaining captured bytes', async () => {
    const { track } = audioFixtures()
    const onRecorded = vi.fn()
    const { result } = renderHook(() => useAudioRecorder(true, onRecorded))
    await act(() => result.current.start())
    await act(async () => track.onended?.())
    expect(result.current.error).toContain('may be incomplete')
    expect(onRecorded).toHaveBeenCalledOnce()
    expect(result.current.phase).toBe('idle')
  })

  it('stops capture before another audio activity takes focus', async () => {
    audioFixtures()
    const onRecorded = vi.fn()
    const { result } = renderHook(() => useAudioRecorder(true, onRecorded))
    await act(() => result.current.start())
    await act(async () => claimAudioFocus({ anotherPlayer: true }))
    expect(onRecorded).toHaveBeenCalledOnce()
    expect(result.current.phase).toBe('idle')
  })

  it('never presents an empty recording as a saved draft', async () => {
    audioFixtures()
    const onRecorded = vi.fn()
    const { result } = renderHook(() => useAudioRecorder(true, onRecorded))
    await act(() => result.current.start())
    currentFixtureRecorder().finalChunk = new Blob([])
    await act(async () => result.current.stop())
    expect(result.current.error).toContain('No audio was captured')
    expect(onRecorded).not.toHaveBeenCalled()
  })

  it('releases tracks when stop fails and permits a later recording', async () => {
    const { track } = audioFixtures()
    const onRecorded = vi.fn()
    const { result } = renderHook(() => useAudioRecorder(true, onRecorded))
    await act(() => result.current.start())
    FixtureRecorder.failStop = true
    act(() => result.current.stop())
    expect(track.stop).toHaveBeenCalledOnce()
    expect(result.current.phase).toBe('idle')
    expect(result.current.error).toContain('Recording could not finish')
    expect(onRecorded).not.toHaveBeenCalled()
    FixtureRecorder.failStop = false
    await act(() => result.current.start())
    expect(result.current.phase).toBe('recording')
  })
})
