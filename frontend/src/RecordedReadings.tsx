import { useCallback, useEffect, useState } from 'react'
import { api, nativeApiUrl } from './api'
import { AudioPlayer, AudioRecorder } from './AudioRecorder'
import { ErrorNotice, Icon, Modal, Spinner } from './components'
import { useRequest } from './useRequest'
import type { ReadAloud, ReadingSelection, RecordedReading } from './voice'
import './recorded-readings.css'

function ReadingDialog({ selection, onClose }: { selection: ReadingSelection; onClose: () => void }) {
  const [reading, setReading] = useState<RecordedReading | null>(null)
  const [ready, setReady] = useState(false)
  const [revision, setRevision] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [recording, setRecording] = useState(false)
  const [consent, setConsent] = useState(false)
  const [confirmRemoval, setConfirmRemoval] = useState(false)
  const [notice, setNotice] = useState('')
  const { pending: loading, error: loadError, run: load, cancel: cancelLoad } = useRequest()
  const mutation = useRequest()
  const editable = ready && (reading === null || reading.ownership.can_edit)

  useEffect(() => {
    setReady(false)
    setReading(null)
    void load((signal) => api<{ reading: RecordedReading | null }>('/readings/lookup', {
      method: 'POST', body: { text: selection.text, language: selection.language }, signal,
    }), (result) => { setReading(result.reading); setReady(true) })
    return cancelLoad
  }, [selection.text, selection.language, revision, load, cancelLoad])

  useEffect(() => {
    if (!file && !recording && !mutation.pending) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [file, recording, mutation.pending])

  const chooseFile = useCallback((next: File | null) => {
    setFile(next)
    setConsent(false)
    setConfirmRemoval(false)
    setNotice('')
  }, [])

  function close() {
    if ((file || recording) && !window.confirm('Discard this unsaved voice recording?')) return
    onClose()
  }

  function refresh() {
    setConfirmRemoval(false)
    mutation.clearError()
    setRevision((value) => value + 1)
  }

  function save() {
    if (!editable || !file || !consent || recording || mutation.pending) return
    const form = new FormData()
    form.append('file', file)
    form.append('fields', JSON.stringify(reading
      ? { share_consent: true }
      : { text: selection.text, language: selection.language, share_consent: true }))
    setNotice('')
    void mutation.run((signal) => api<RecordedReading>(reading ? `/readings/${encodeURIComponent(reading.id)}/audio` : '/readings/audio', {
      method: reading ? 'PATCH' : 'POST', body: form, signal, timeout: 60000,
    }), (saved) => {
      setReading(saved)
      setFile(null)
      setConsent(false)
      setConfirmRemoval(false)
      setNotice('Your voice recording is saved. All signed-in users can listen to it.')
    })
  }

  function remove() {
    if (!reading?.ownership.can_edit || !confirmRemoval || mutation.pending || recording) return
    const identifier = reading.id
    void mutation.run((signal) => api<void>(`/readings/${encodeURIComponent(identifier)}`, {
      method: 'DELETE', signal,
    }), () => {
      setReading(null)
      setConfirmRemoval(false)
      setNotice('The active reading was removed. Existing backups and older audio files are retained on the server.')
    })
  }

  return <Modal title="Recorded read-aloud" onClose={close} busy={mutation.pending} className="reading-modal">
    <p className="modal-description">Listen to an actual recording for this text, or record your own reading when none exists. No synthetic voice, cloning or automatic transcription is used.</p>
    <pre className="reading-source" aria-label="Text for this reading">{selection.text}</pre>
    <p className="helper-text">Recording language: {selection.language === 'en' ? 'English' : 'French / Camfranglais'}. Case, spacing and apostrophe variants share a reading; punctuation and language stay separate.</p>
    <ErrorNotice message={loadError} onRetry={refresh} />
    <ErrorNotice message={mutation.error} />
    {loading && <p className="lab-loading" role="status"><Spinner label="Loading recorded reading" />Looking for a saved voice recording...</p>}
    {notice && <p className="notice notice-success" role="status">{notice}</p>}
    {ready && (reading ? <section aria-label="Saved voice recording">
      <h3>Saved reading</h3>
      <p className="lab-copy">Creator: {reading.ownership.owner_name}. {reading.ownership.can_edit ? 'You can replace or remove this reading.' : 'Only its creator can replace or remove it.'}</p>
      <AudioPlayer src={nativeApiUrl(`/readings/${encodeURIComponent(reading.id)}/audio`)} filename={reading.audio_filename} autoPlay disabled={mutation.pending || recording || Boolean(file)} />
      {reading.ownership.can_edit && !file && <button type="button" className="text-button" disabled={recording || mutation.pending} onClick={() => setConfirmRemoval(true)}><Icon name="trash" size={16} />Remove saved reading</button>}
      {confirmRemoval && <div className="notice notice-subtle"><p>Remove this shared reading for everyone? Backup copies are retained.</p><button type="button" className="button button-danger" disabled={mutation.pending || recording || Boolean(file)} onClick={remove}>Yes, remove reading</button><button type="button" className="text-button" disabled={mutation.pending} onClick={() => setConfirmRemoval(false)}>Keep reading</button></div>}
    </section> : <p className="notice notice-subtle" role="status">No voice recording is saved for this text yet. Record your reading or attach an audio file below.</p>)}
    {(editable || file) && <section aria-label="Your voice recording">
      <h3>{reading ? 'Record a replacement' : 'Record your reading'}</h3>
      {!editable && file && <p className="notice notice-subtle">This reading cannot currently be changed. Your unsaved audio is still available to download.</p>}
      <AudioRecorder key={reading?.audio_filename ?? 'new-reading'} file={file} onFile={chooseFile} onBusyChange={setRecording} disabled={!editable || mutation.pending} />
      <p className="helper-text">Read the displayed words yourself. Pronunciation recordings do not create Collection entries or analyzer tests. Audio stays local until you explicitly save it.</p>
      <label className="checkbox-label"><input type="checkbox" checked={consent} disabled={!editable || !file || recording || mutation.pending} onChange={(event) => setConsent(event.target.checked)} /><span>I recorded this voice or have permission to share it with all signed-in users.</span></label>
      <button type="button" className="button button-primary reading-save" disabled={!editable || !file || !consent || recording || mutation.pending} onClick={save}>{mutation.pending ? <Spinner label="Saving recorded reading" /> : <Icon name="check" size={16} />}{mutation.pending ? 'Saving...' : reading ? 'Replace saved reading' : 'Save voice recording'}</button>
    </section>}
    <div className="modal-footer"><button type="button" className="text-button" disabled={loading || mutation.pending || recording} onClick={refresh}><Icon name="refresh" size={16} />Refresh recorded reading</button><button type="button" className="button button-secondary" disabled={mutation.pending} onClick={close}>Done</button></div>
  </Modal>
}

export function RecordedReadings({ speech }: { speech: ReadAloud }) {
  return speech.selection && <ReadingDialog key={`${speech.selection.id}:${speech.selection.language}:${speech.selection.text}`} selection={speech.selection} onClose={speech.stop} />
}
