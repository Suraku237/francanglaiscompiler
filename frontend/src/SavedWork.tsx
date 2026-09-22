import { useEffect, useState } from 'react'
import { api } from './api'
import type { HistoryItem, HistorySummary } from './accountTypes'
import { ErrorNotice, Spinner } from './components'
import { useRequest } from './useRequest'
import { useDownload } from './useDownload'

export function SavedWork({ active, onUseText }: { active: boolean; onUseText: (text: string) => void }) {
  const [entries, setEntries] = useState<HistorySummary[]>([])
  const [selected, setSelected] = useState<HistoryItem | null>(null)
  const [query, setQuery] = useState('')
  const [title, setTitle] = useState('')
  const request = useRequest()
  const actions = useRequest()
  const download = useDownload()
  const { run, cancel } = request
  useEffect(() => {
    if (!active) return
    void run((signal) => api<{ entries: HistorySummary[] }>('/workspace/history', { signal }), (value) => setEntries(value.entries))
    return cancel
  }, [active, run, cancel])
  const refresh = () => {
    cancel()
    void run((signal) => api<{ entries: HistorySummary[] }>('/workspace/history', { signal }), (value) => setEntries(value.entries))
  }
  const displayed = entries.filter((entry) => entry.title.toLocaleLowerCase().includes(query.toLocaleLowerCase()))
  return <section className="page saved-work" aria-labelledby="history-title">
    <div className="page-intro"><div><div className="eyebrow">LEGACY SAVED WORK</div><h1 id="history-title">History</h1><p>Read, export or remove translations and conversations saved before the compiler-only workspace. No new translation or assistant requests are made.</p></div>
      <button type="button" className="button button-secondary" onClick={refresh} disabled={request.pending}>Refresh history</button></div>
    <ErrorNotice message={request.error || actions.error || download.error} />
    <label>Search saved work<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
    {request.pending && <Spinner label="Loading saved work" />}
    {!request.pending && !entries.length && <div className="workspace-section"><h2>No legacy saved work</h2><p>There are no historical items in this project. Save current collection entries in Collection and grammar/report writing in Compiler lab.</p></div>}
    {selected && <div className="workspace-section" aria-label="Saved work details">
      <h2>{selected.title}</h2>
      <p>{selected.kind === 'translation' ? 'Legacy translation' : 'Legacy conversation'} · {new Date(selected.created_at).toLocaleString()}</p>
      <p className="notice notice-subtle">Historical content may contain generated or unverified material. It is not your research corpus and is never counted as fieldwork.</p>
      {selected.kind === 'translation'
        ? <><h3>Source</h3><pre>{selected.content.source_text}</pre><h3>Translation</h3><pre>{selected.content.translation}</pre><p>{selected.content.explanation}</p><p>{selected.content.note}</p></>
        : selected.content.messages.map((message, index) => <div key={index}><strong>{message.role === 'user' ? 'Saved user message' : 'Legacy assistant reply'}</strong><pre>{message.content}</pre></div>)}
      <label>Saved title<input maxLength={100} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <div className="workspace-actions">
        <button type="button" className="button button-secondary" disabled={actions.pending || !title.trim()} onClick={() => {
          void actions.run((signal) => api<HistoryItem>(`/workspace/history/${selected.id}`, { method: 'PATCH', body: { name: title }, signal }), (next) => { setSelected(next); refresh() })
        }}>Rename saved work</button>
        <button type="button" className="button button-secondary" onClick={() => {
          const text = selected.kind === 'translation' ? selected.content.source_text : selected.content.messages.filter((message) => message.role === 'user').at(-1)?.content
          if (text) onUseText(text)
        }}>Use source in compiler</button>
        <button type="button" className="button button-secondary" onClick={() => download.download(new Blob([JSON.stringify(selected, null, 2)], { type: 'application/json' }), 'mboa-saved-work.json')}>Download saved work</button>
        <button type="button" className="button button-danger" disabled={actions.pending} onClick={() => {
          if (!window.confirm('Delete this saved item? Existing backups may still contain it.')) return
          void actions.run((signal) => api(`/workspace/history/${selected.id}`, { method: 'DELETE', signal }), () => { setSelected(null); refresh() })
        }}>Delete saved work</button>
      </div>
    </div>}
    <div className="workspace-section"><h2>Saved items ({displayed.length})</h2>
      {displayed.map((entry) => <div className="workspace-row" key={entry.id}><div><strong>{entry.title}</strong><p>Legacy {entry.kind} · {new Date(entry.created_at).toLocaleDateString()}</p></div>
        <button type="button" className="button button-secondary" disabled={actions.pending} onClick={() => {
          void actions.run((signal) => api<HistoryItem>(`/workspace/history/${entry.id}`, { signal }), (value) => { setSelected(value); setTitle(value.title) })
        }} aria-label={`Open ${entry.title}`}>Open</button></div>)}
    </div>
  </section>
}
