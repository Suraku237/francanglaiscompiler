import { vi } from 'vitest'

export class FixtureRecorder {
  static instances: FixtureRecorder[] = []
  static failStart = false
  static failStop = false
  static isTypeSupported = (type: string) => type.startsWith('audio/webm')
  state: RecordingState = 'inactive'
  mimeType = 'audio/webm;codecs=opus'
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: (() => void) | null = null
  finalChunk = new Blob(['Synthetic audio bytes; not a physical recording.'], { type: this.mimeType })
  constructor() { FixtureRecorder.instances.push(this) }
  start = vi.fn(() => {
    if (FixtureRecorder.failStart) throw new DOMException('Device failure', 'NotReadableError')
    this.state = 'recording'
  })
  stop = vi.fn(() => {
    if (FixtureRecorder.failStop) throw new DOMException('Stop failure', 'InvalidStateError')
    this.state = 'inactive'
    queueMicrotask(() => {
      this.ondataavailable?.({ data: this.finalChunk })
      this.onstop?.()
    })
  })
}

export function audioFixtures() {
  FixtureRecorder.instances = []
  FixtureRecorder.failStart = false
  FixtureRecorder.failStop = false
  const track = { stop: vi.fn(), onended: null as (() => void) | null }
  const stream = { getAudioTracks: () => [track], getTracks: () => [track] }
  const getUserMedia = vi.fn(() => Promise.resolve(stream))
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
  vi.stubGlobal('MediaRecorder', FixtureRecorder)
  vi.stubGlobal('isSecureContext', true)
  const BaseURL = URL
  const createObjectURL = vi.fn(() => 'blob:synthetic-audio-fixture')
  const revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', class extends BaseURL {
    static createObjectURL = createObjectURL
    static revokeObjectURL = revokeObjectURL
  })
  return { track, stream, getUserMedia, createObjectURL, revokeObjectURL }
}

export function currentFixtureRecorder(): FixtureRecorder {
  const recorder = FixtureRecorder.instances.at(-1)
  if (!recorder) throw new Error('Expected a recording session in this test.')
  return recorder
}
