import { useCallback, useEffect, useRef, useState } from 'react'
import { AUDIO_FOCUS_EVENT, claimAudioFocus, hasAudioFocus } from './audioFocus'
import { MAX_IMPORT_BYTES } from './importTypes'

type Phase = 'idle' | 'requesting' | 'recording' | 'stopping'

interface RecordingSession {
  recorder: MediaRecorder
  stream: MediaStream
  chunks: Blob[]
  bytes: number
  overLimit: boolean
  timer: number | null
}

const mimeOptions = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg;codecs=opus']
const extensions: Record<string, string> = {
  'audio/webm': 'webm', 'video/webm': 'webm', 'audio/mp4': 'm4a',
  'video/mp4': 'm4a', 'audio/ogg': 'ogg',
}

function releaseTracks(session: RecordingSession) {
  if (session.timer !== null) window.clearInterval(session.timer)
  for (const track of session.stream.getTracks()) {
    track.onended = null
    track.stop()
  }
}

function discardSession(session: RecordingSession) {
  session.recorder.ondataavailable = null
  session.recorder.onerror = null
  session.recorder.onstop = null
  try {
    if (session.recorder.state !== 'inactive') session.recorder.stop()
  } finally {
    releaseTracks(session)
  }
}

function recordingError(cause: unknown): string {
  if (cause instanceof DOMException) {
    const messages: Record<string, string> = {
      NotAllowedError: 'Microphone permission was denied. Allow access in site settings, or attach an existing recording.',
      NotFoundError: 'No microphone was found. Connect one, or attach an existing recording.',
      NotReadableError: 'The microphone is unavailable or in use. Close other recording apps and try again.',
      SecurityError: 'Microphone access is blocked. Use HTTPS or localhost and check your browser settings.',
      NotSupportedError: 'This browser cannot record a supported audio format. Attach an existing recording instead.',
    }
    const message = messages[cause.name]
    if (message) return message
  }
  return 'Recording could not start. Check the microphone and browser permissions, then try again.'
}

export function useAudioRecorder(active: boolean, onRecorded: (file: File) => void) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState('')
  const session = useRef<RecordingSession | null>(null)
  const requesting = useRef(false)
  const generation = useRef(0)
  const callback = useRef(onRecorded)
  const supported = window.isSecureContext &&
    typeof navigator.mediaDevices?.getUserMedia === 'function' && typeof window.MediaRecorder === 'function'
  useEffect(() => { callback.current = onRecorded }, [onRecorded])

  const cancel = useCallback(() => {
    generation.current += 1
    requesting.current = false
    const current = session.current
    session.current = null
    try {
      if (current) discardSession(current)
    } catch {
      setError('The recorder could not stop normally. Microphone tracks were released; please retry.')
    } finally {
      setPhase('idle')
    }
  }, [])

  const stop = useCallback(() => {
    const current = session.current
    if (!current) {
      cancel()
      return
    }
    if (current.recorder.state === 'inactive') return
    setPhase('stopping')
    try {
      current.recorder.stop()
    } catch {
      cancel()
      setError('Recording could not finish. The microphone was released; your previous attachment is unchanged.')
    }
  }, [cancel])

  const start = useCallback(async () => {
    if (!active || session.current || requesting.current || phase !== 'idle') return
    if (!supported) {
      setError('Audio recording needs HTTPS or localhost and a browser with MediaRecorder support. You can attach an audio file instead.')
      return
    }
    const attempt = ++generation.current
    requesting.current = true
    setError('')
    setSeconds(0)
    setPhase('requesting')
    let stream: MediaStream | null = null
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      if (generation.current !== attempt) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      requesting.current = false
      if (!stream.getAudioTracks().length) throw new DOMException('No audio track', 'NotFoundError')
      const mimeType = typeof MediaRecorder.isTypeSupported === 'function'
        ? mimeOptions.find((mime) => MediaRecorder.isTypeSupported(mime))
        : undefined
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      const current: RecordingSession = { recorder, stream, chunks: [], bytes: 0, overLimit: false, timer: null }
      session.current = current
      recorder.ondataavailable = ({ data }) => {
        if (session.current !== current || !data.size || current.overLimit) return
        current.bytes += data.size
        if (current.bytes > MAX_IMPORT_BYTES) {
          current.overLimit = true
          current.chunks = []
          setError('Recording exceeded 12 MB and was not attached. Make a shorter recording; your previous attachment is unchanged.')
          stop()
          return
        }
        current.chunks.push(data)
      }
      recorder.onstop = () => {
        if (session.current !== current) return
        session.current = null
        releaseTracks(current)
        setPhase('idle')
        if (current.overLimit) return
        if (!current.bytes) {
          setError('No audio was captured. Check the microphone and try again.')
          return
        }
        const type = (recorder.mimeType || current.chunks[0]?.type || '').toLowerCase()
        const extension = extensions[type.split(';')[0] ?? '']
        if (!extension) {
          setError('The browser produced an unsupported recording format. Attach WAV, MP3, M4A, OGG, FLAC or WebM instead.')
          return
        }
        const file = new File(current.chunks, `recording-${Date.now()}.${extension}`, { type })
        callback.current(file)
      }
      recorder.onerror = () => {
        if (session.current !== current) return
        setError('The recorder reported an error. Any captured audio is kept for review below; it may be incomplete.')
        stop()
      }
      for (const track of stream.getAudioTracks()) {
        track.onended = () => {
          if (session.current !== current) return
          setError('The microphone disconnected. Review the captured audio below; the recording may be incomplete.')
          stop()
        }
      }
      claimAudioFocus(current)
      recorder.start(1000)
      const started = Date.now()
      current.timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 500)
      setPhase('recording')
    } catch (cause: unknown) {
      if (generation.current !== attempt) return
      requesting.current = false
      const current = session.current
      session.current = null
      if (current) {
        try {
          discardSession(current)
        } catch (cleanupError: unknown) {
          console.error('Unable to close a failed recording session.', cleanupError)
        }
      } else {
        stream?.getTracks().forEach((track) => track.stop())
      }
      setPhase('idle')
      setError(recordingError(cause))
    }
  }, [active, phase, stop, supported])

  useEffect(() => {
    if (!active) stop()
  }, [active, stop])

  useEffect(() => {
    const onVisibility = () => { if (document.hidden) stop() }
    const onFocus = (event: Event) => {
      if (!hasAudioFocus(event, session.current)) stop()
    }
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener(AUDIO_FOCUS_EVENT, onFocus)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener(AUDIO_FOCUS_EVENT, onFocus)
      generation.current += 1
      requesting.current = false
      const current = session.current
      session.current = null
      if (current) {
        try {
          discardSession(current)
        } catch (cause: unknown) {
          console.error('Unable to close the recording session; microphone tracks were released.', cause)
        }
      }
    }
  }, [stop])

  return { phase, seconds, error, supported, busy: phase !== 'idle', start, stop, cancel }
}
