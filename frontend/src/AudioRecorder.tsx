import { useEffect, useRef, useState } from 'react'
import { AUDIO_FOCUS_EVENT, claimAudioFocus, hasAudioFocus } from './audioFocus'
import { ErrorNotice, Icon, Spinner } from './components'
import { MAX_IMPORT_BYTES } from './importTypes'
import { useAudioRecorder } from './useAudioRecorder'
import './audio.css'

export const AUDIO_ACCEPT = '.wav,.mp3,.m4a,.ogg,.flac,.webm'
export function isAudioFile(file: File): boolean {
  return /\.(wav|mp3|m4a|ogg|flac|webm)$/i.test(file.name)
}

export function AudioPlayer({ src, filename, active = true, disabled = false }: {
  src: string
  filename: string
  active?: boolean
  disabled?: boolean
}) {
  const player = useRef<HTMLAudioElement>(null)
  const [error, setError] = useState('')
  useEffect(() => { setError('') }, [src])
  useEffect(() => {
    if ((!active || disabled) && player.current && !player.current.paused) player.current.pause()
  }, [active, disabled])
  useEffect(() => {
    const onFocus = (event: Event) => {
      const current = player.current
      if (current && !hasAudioFocus(event, current) && !current.paused) current.pause()
    }
    window.addEventListener(AUDIO_FOCUS_EVENT, onFocus)
    const current = player.current
    return () => {
      window.removeEventListener(AUDIO_FOCUS_EVENT, onFocus)
      if (current && !current.paused) current.pause()
    }
  }, [])
  return <div className="audio-player">
    <audio key={`${src}:${filename}`} ref={player} src={src} controls={!disabled} tabIndex={disabled ? -1 : 0} preload="none" aria-label={`Play recording: ${filename}`} onPlay={() => {
      if (!player.current) return
      if (disabled || !active) player.current.pause()
      else claimAudioFocus(player.current)
    }} onError={() => setError('This recording could not be played. It may be missing, damaged or unsupported by this browser. Download it to check with another player.')} />
    <a href={src} download={filename}>Download audio</a>
    <ErrorNotice message={error} />
  </div>
}

export function AudioRecorder({ active = true, disabled = false, file, onFile, onBusyChange, showPicker = true }: {
  active?: boolean
  disabled?: boolean
  file: File | null
  onFile: (file: File | null) => void
  onBusyChange?: (busy: boolean) => void
  showPicker?: boolean
}) {
  const recorder = useAudioRecorder(active, onFile)
  const [validation, setValidation] = useState('')
  const [url, setUrl] = useState('')
  const picker = useRef<HTMLInputElement>(null)
  useEffect(() => { onBusyChange?.(recorder.busy) }, [onBusyChange, recorder.busy])
  useEffect(() => {
    if (!file) { setUrl(''); return }
    const objectUrl = URL.createObjectURL(file)
    setUrl(objectUrl)
    return () => URL.revokeObjectURL(objectUrl)
  }, [file])
  const minutes = Math.floor(recorder.seconds / 60).toString().padStart(2, '0')
  const seconds = (recorder.seconds % 60).toString().padStart(2, '0')
  return <div className="audio-recorder" aria-label="Local audio recording">
    <div className="audio-recorder-heading"><Icon name="mic" size={20} /><div><strong>Record or attach audio</strong><p>Captured locally, without speech recognition or automatic upload. Maximum 12 MB.</p></div></div>
    <div className="audio-recorder-actions">
      {recorder.phase === 'idle' ? <button type="button" className="button button-secondary" disabled={disabled || !active || !recorder.supported} onClick={() => { setValidation(''); void recorder.start() }}><Icon name="mic" size={17} />Record audio</button> :
        <button type="button" className="button button-secondary" disabled={recorder.phase === 'stopping'} onClick={recorder.phase === 'requesting' ? recorder.cancel : recorder.stop}>{recorder.phase === 'requesting' ? <Spinner label="Waiting for microphone permission" /> : <Icon name="stop" size={17} />}{recorder.phase === 'requesting' ? 'Cancel microphone request' : recorder.phase === 'stopping' ? 'Finishing recording...' : 'Stop recording'}</button>}
      <span className="audio-timer" role="status">{recorder.phase === 'recording' ? `Recording ${minutes}:${seconds}` : recorder.phase === 'stopping' ? 'Preparing your recording' : recorder.phase === 'requesting' ? 'Waiting for permission' : 'Microphone off'}</span>
    </div>
    {!recorder.supported && <p className="helper-text">Recording needs HTTPS or localhost and a browser with MediaRecorder support. You can still attach an existing audio file.</p>}
    {showPicker && <label className="field audio-attachment-field">Attach an audio file<input ref={picker} type="file" accept={AUDIO_ACCEPT} disabled={disabled || recorder.busy} onChange={(event) => {
      const selected = event.target.files?.[0]
      if (!selected) return
      if (!isAudioFile(selected) || !selected.size || selected.size > MAX_IMPORT_BYTES) {
        setValidation(!isAudioFile(selected) ? 'Choose WAV, MP3, M4A, OGG, FLAC or WebM audio.' : !selected.size ? 'This audio file is empty.' : 'This audio file exceeds 12 MB.')
        event.target.value = ''
        return
      }
      setValidation('')
      onFile(selected)
    }} /></label>}
    {file && <div className="audio-draft">
      <p><strong>Draft audio:</strong> {file.name} ({(file.size / 1024).toFixed(1)} KB)</p>
      {url && <AudioPlayer src={url} filename={file.name} active={active} disabled={disabled || recorder.busy} />}
      <button type="button" className="text-button" disabled={disabled || recorder.busy} onClick={() => {
        if (picker.current) picker.current.value = ''
        setValidation('')
        onFile(null)
      }}>Discard draft audio</button>
    </div>}
    <ErrorNotice message={validation || recorder.error} />
  </div>
}
