import { useEffect, useRef, useState } from 'react'
import { api, ApiError, errorDetail, isCancelled, nativeApiUrl } from './api'
import { ErrorNotice, Icon, Modal, Spinner } from './components'
import type { Screenshot } from './courseworkTypes'
import { useRequest } from './useRequest'

async function downloadBundle(signal: AbortSignal): Promise<Blob> {
  const controller = new AbortController()
  let timedOut = false
  const cancel = () => controller.abort()
  if (signal.aborted) controller.abort()
  signal.addEventListener('abort', cancel, { once: true })
  const timer = window.setTimeout(() => { timedOut = true; controller.abort() }, 120000)
  try {
    const response = await fetch(nativeApiUrl('/coursework/export'), { signal: controller.signal, cache: 'no-store', credentials: 'same-origin' })
    if (controller.signal.aborted) throw new DOMException('Request cancelled', 'AbortError')
    if (response.status === 401) window.dispatchEvent(new Event('mboa:session-expired'))
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null)
      throw new ApiError(errorDetail(body) ?? `The draft export failed (${response.status}). Save your project and check the grammar before trying again.`, response.status)
    }
    if (!response.headers.get('content-type')?.includes('application/zip')) {
      throw new Error('The server did not return a ZIP file. Check the backend and try again.')
    }
    const blob = await response.blob()
    if (controller.signal.aborted) throw new DOMException('Request cancelled', 'AbortError')
    if (!blob.size) throw new Error('The export was empty. Please try again.')
    return blob
  } catch (error: unknown) {
    if (timedOut) throw new Error('The draft export timed out. Check the backend and try again.')
    if (isCancelled(error)) throw error
    if (error instanceof TypeError) throw new Error('Cannot download from the application server. Check the connection and try again.')
    throw error
  } finally {
    window.clearTimeout(timer)
    signal.removeEventListener('abort', cancel)
  }
}

export function CourseworkExport({ active, dirty, busy }: { active: boolean; dirty: boolean; busy: boolean }) {
  const { pending, error, run, cancel, clearError } = useRequest()
  const [downloaded, setDownloaded] = useState(false)
  const downloads = useRef<{ url: string; timer: number }[]>([])
  useEffect(() => {
    if (!active || dirty || busy) {
      cancel()
      clearError()
      setDownloaded(false)
    }
  }, [active, dirty, busy, cancel, clearError])
  useEffect(() => () => {
    for (const download of downloads.current) {
      window.clearTimeout(download.timer)
      URL.revokeObjectURL(download.url)
    }
  }, [])

  function exportDraft() {
    if (dirty || busy || pending) return
    setDownloaded(false)
    void run(downloadBundle, (blob) => {
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'francanglais-coursework.zip'
      document.body.appendChild(link)
      link.click()
      link.remove()
      const timer = window.setTimeout(() => {
        URL.revokeObjectURL(url)
        downloads.current = downloads.current.filter((item) => item.url !== url)
      }, 1000)
      downloads.current.push({ url, timer })
      setDownloaded(true)
    })
  }

  return <div className="lab-export">
    <div className="lab-result-heading"><h3>Download report, source code & presentation</h3></div>
    <p className="lab-copy">The ZIP is computed on this server from the <strong>selected project’s saved profile, grammar, collection entries, and attached screenshots</strong>. It never uses unsaved manual tests or legacy history.</p>
    <details className="lab-disclosure"><summary>Export contents & submission requirements</summary><div className="lab-disclosure-body">
    <ul className="lab-list">
      <li><strong>report.html:</strong> a 25-section printable draft. Review it, then print to PDF; check the final layout reaches 25–30 pages and does not exceed 30.</li>
      <li><strong>presentation.pptx:</strong> a 10-minute draft. Rehearse the live demo and allocate about 3 minutes to each of 3 students.</li>
      <li><strong>Evidence:</strong> raw-data, token, frequency, variation and acceptance CSVs; grammar, FIRST/FOLLOW, table and trace JSON; attached screenshots.</li>
      <li><strong>Implementation:</strong> actual source code and generated unittest cases using your saved corpus. Review and run those tests before submission.</li>
    </ul>
    <p className="lab-copy">This is a draft. Check the fieldwork, grammar, writing and final page count before submission.</p>
    </div></details>
    {dirty && <p className="lab-unsaved" role="status">Save project first: the export cannot include your unsaved edits.</p>}
    <ErrorNotice message={error} />
    <div className="lab-actions"><button type="button" className="button button-primary" disabled={dirty || busy || pending} onClick={exportDraft}>{pending ? <Spinner label="Building coursework ZIP" /> : <Icon name="collection" size={17} />}{pending ? 'Preparing draft…' : 'Download coursework draft (.zip)'}</button>{pending && <button type="button" className="text-button" onClick={cancel}>Cancel download</button>}</div>
    {downloaded && <p className="lab-save-notice" role="status">Draft download started. Open the ZIP and review every deliverable before submission.</p>}
  </div>
}

export function CourseworkScreenshots({ screenshots, onChanged, busy, onBusyChange }: {
  screenshots: Screenshot[]
  onChanged: (update: (items: Screenshot[]) => Screenshot[]) => void
  busy: boolean
  onBusyChange: (busy: boolean) => void
}) {
  const [name, setName] = useState('')
  const [dataUrl, setDataUrl] = useState('')
  const [fileName, setFileName] = useState('')
  const [fileError, setFileError] = useState('')
  const [reading, setReading] = useState(false)
  const [notice, setNotice] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Screenshot | null>(null)
  const reader = useRef<FileReader | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const upload = useRequest()
  const removal = useRequest()
  useEffect(() => () => { reader.current?.abort() }, [])
  useEffect(() => { onBusyChange(upload.pending || removal.pending) }, [upload.pending, removal.pending, onBusyChange])

  function chooseFile(file: File | undefined) {
    reader.current?.abort()
    reader.current = null
    setDataUrl('')
    setFileName('')
    setFileError('')
    setNotice('')
    upload.clearError()
    setReading(false)
    if (!file) return
    if (!['image/png', 'image/jpeg'].includes(file.type)) {
      setFileError('Choose a PNG or JPEG image. Other file types are not accepted.')
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      setFileError('This image exceeds 2 MB. Resize it or capture a smaller area before uploading.')
      return
    }
    const nextReader = new FileReader()
    reader.current = nextReader
    setName(file.name.replace(/\.(png|jpe?g)$/i, '').slice(0, 120))
    setReading(true)
    nextReader.onload = () => {
      if (reader.current !== nextReader) return
      const value = nextReader.result
      setReading(false)
      if (typeof value !== 'string' || value.length > 2800000) {
        setFileError('The encoded image is too large. Resize it and try again.')
        return
      }
      setDataUrl(value)
      setFileName(file.name)
    }
    nextReader.onerror = () => {
      if (reader.current === nextReader) {
        setReading(false)
        setFileError('This file could not be read. Choose it again or try a different image.')
      }
    }
    nextReader.readAsDataURL(file)
  }

  return <div className="lab-screenshots">
    <h3>Screenshots of the working analyzer</h3>
    <p className="lab-copy">Attach actual captures of token tables, grammar transformations, the parsing table and parser trace for your report.</p>
    <form className="lab-upload" onSubmit={(event) => {
      event.preventDefault()
      if (!dataUrl || !name.trim() || upload.pending || removal.pending || busy) return
      setNotice('')
      void upload.run((signal) => api<Screenshot>('/coursework/screenshots', { method: 'POST', body: { name: name.trim(), data_url: dataUrl }, signal, timeout: 30000 }), (screenshot) => {
        onChanged((items) => [...items.filter((item) => item.id !== screenshot.id), screenshot])
        setDataUrl('')
        setFileName('')
        setName('')
        if (input.current) input.current.value = ''
        setNotice('Screenshot saved privately in this project. It will be included in the next draft export.')
      })
    }}>
      <div className="lab-two-columns">
        <div className="field"><label htmlFor="lab-screenshot-file">Choose PNG or JPEG · max 2 MB</label><input ref={input} id="lab-screenshot-file" type="file" accept="image/png,image/jpeg" disabled={upload.pending || busy} onChange={(event) => chooseFile(event.target.files?.[0])} />{reading && <span className="field-hint"><Spinner label="Reading screenshot" /> Reading image…</span>}</div>
        <div className="field"><label htmlFor="lab-screenshot-name">Screenshot caption</label><input id="lab-screenshot-name" maxLength={120} value={name} disabled={upload.pending || busy} onChange={(event) => { setName(event.target.value); upload.clearError() }} placeholder="Describe the evidence shown…" /></div>
      </div>
      {dataUrl && <div className="lab-image-preview"><img src={dataUrl} alt={`Selected screenshot: ${name || fileName}`} /><span>Preview only · not uploaded yet</span></div>}
      <ErrorNotice message={fileError || upload.error} />
      <button type="submit" className="button button-secondary" disabled={!dataUrl || !name.trim() || upload.pending || removal.pending || busy || reading}>{upload.pending ? <Spinner label="Uploading screenshot" /> : <Icon name="plus" size={17} />}{upload.pending ? 'Saving screenshot…' : 'Save screenshot to project'}</button>
    </form>
    {notice && <p className="lab-save-notice" role="status">{notice}</p>}
    {!screenshots.length ? <p className="lab-copy lab-empty">No screenshots attached. A placeholder or generated image is not evidence of a running analyzer.</p> : <div className="lab-screenshot-grid">{screenshots.map((screenshot) => <figure key={screenshot.id}>
      <a href={screenshot.url} target="_blank" rel="noreferrer" aria-label={`Open screenshot: ${screenshot.name}`}><img src={screenshot.url} alt={screenshot.name} loading="lazy" /></a>
      <figcaption><span>{screenshot.name}</span><button type="button" className="icon-button delete-button" aria-label={`Remove screenshot: ${screenshot.name}`} disabled={upload.pending || removal.pending || busy} onClick={() => { removal.clearError(); setDeleteTarget(screenshot) }}><Icon name="trash" size={17} /></button></figcaption>
    </figure>)}</div>}
    {deleteTarget && <Modal title="Remove this screenshot?" onClose={() => setDeleteTarget(null)} busy={removal.pending} className="delete-modal">
      <p className="modal-description">“{deleteTarget.name}” will be removed from this project and future exports. This does not remove your original image file or existing backups.</p>
      <ErrorNotice message={removal.error} />
      <div className="modal-footer"><button type="button" className="button button-secondary" onClick={() => setDeleteTarget(null)} disabled={removal.pending}>Keep screenshot</button><button type="button" className="button button-danger" disabled={removal.pending} onClick={() => {
        const target = deleteTarget
        void removal.run((signal) => api<void>(`/coursework/screenshots/${encodeURIComponent(target.id)}`, { method: 'DELETE', signal }), () => {
          onChanged((items) => items.filter((item) => item.id !== target.id))
          setDeleteTarget(null)
          setNotice('Screenshot removed from this project’s evidence.')
        })
      }}>{removal.pending ? <Spinner label="Removing screenshot" /> : <Icon name="trash" size={17} />}Remove screenshot</button></div>
    </Modal>}
  </div>
}
