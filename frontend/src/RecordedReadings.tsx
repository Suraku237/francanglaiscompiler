import { useEffect, useState } from 'react'
import { api, nativeApiUrl } from './api'
import { AudioPlayer } from './AudioRecorder'
import { ErrorNotice, Icon, Modal, Spinner } from './components'
import { useRequest } from './useRequest'
import type { ReadAloud, ReadingSelection, RecordedReading } from './voice'
import './recorded-readings.css'

function ReadingDialog({ selection, onClose }: { selection: ReadingSelection; onClose: () => void }) {
  const [reading, setReading] = useState<RecordedReading | null>(null)
  const [ready, setReady] = useState(false)
  const [revision, setRevision] = useState(0)
  const { pending: loading, error, run: load, cancel: cancelLoad } = useRequest()

  useEffect(() => {
    setReady(false)
    setReading(null)
    void load((signal) => api<{ reading: RecordedReading | null }>('/readings/lookup', {
      method: 'POST', body: { text: selection.text, language: selection.language }, signal,
    }), (result) => { setReading(result.reading); setReady(true) })
    return cancelLoad
  }, [selection.text, selection.language, revision, load, cancelLoad])

  return <Modal title="Recorded read-aloud" onClose={onClose} className="reading-modal">
    <p className="modal-description">Listen to an existing recording for this text. Recordings are read-only. No synthetic voice, cloning or automatic transcription is used.</p>
    <div className="reading-body">
      <pre className="reading-source" aria-label="Text for this reading">{selection.text}</pre>
      <p className="helper-text">Recording language: {selection.language === 'en' ? 'English' : 'French / Camfranglais'}. Case, spacing and apostrophe variants share a reading; punctuation and language stay separate.</p>
      <ErrorNotice message={error} onRetry={() => setRevision((value) => value + 1)} />
      {loading && <p className="lab-loading" role="status"><Spinner label="Loading recorded reading" />Looking for a saved voice recording...</p>}
      {ready && (reading ? <section aria-label="Saved voice recording">
        <h3>Saved reading</h3>
        <p className="lab-copy">Public recording · Read-only.</p>
        <AudioPlayer src={nativeApiUrl(`/readings/${encodeURIComponent(reading.id)}/audio`)} filename={reading.audio_filename} autoPlay />
      </section> : <p className="notice notice-subtle" role="status">No voice recording is available for this text. Recordings are read-only; recording and uploads are unavailable.</p>)}
    </div>
    <div className="modal-footer"><button type="button" className="text-button" disabled={loading} onClick={() => setRevision((value) => value + 1)}><Icon name="refresh" size={16} />Refresh recorded reading</button><button type="button" className="button button-secondary" onClick={onClose}>Done</button></div>
  </Modal>
}

export function RecordedReadings({ speech }: { speech: ReadAloud }) {
  return speech.selection && <ReadingDialog key={`${speech.selection.id}:${speech.selection.language}:${speech.selection.text}`} selection={speech.selection} onClose={speech.stop} />
}
