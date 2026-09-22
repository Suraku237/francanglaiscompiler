import { useEffect, useState } from 'react'
import { api, nativeApiUrl } from './api'
import type { Account, Project, Session } from './accountTypes'
import type { DatasetEntry } from './types'
import { ErrorNotice, Spinner } from './components'
import { useRequest } from './useRequest'

interface Revision {
  id: string
  entry_id: string
  action: string
  timestamp: string
  data: DatasetEntry
}
interface Revisions { revisions: Revision[]; workspace_version: number }
interface Backup { id: string; created_at: string; kind: string; size: number }
interface BackupConfig { automatic: boolean; interval_hours: 24 | 168; keep_last: number }
interface BackupState {
  backups: Backup[]
  settings: BackupConfig
  state: { last_success?: number; last_error?: string }
  workspace_version: number
}
interface Preview {
  token: string
  expires_at: number
  workspace_version: number
  counts: Record<string, number>
  warnings: string[]
}

export function WorkspaceSettings({ active, account, googleEnabled, projects, selectedProject, onProfileChanged }: {
  active: boolean
  account?: Account
  googleEnabled?: boolean
  projects: Project[]
  selectedProject: string
  onProfileChanged?: (session: Session) => void
}) {
  const [projectName, setProjectName] = useState('')
  const [displayName, setDisplayName] = useState(account?.display_name ?? '')
  const [renaming, setRenaming] = useState('')
  const [renameValue, setRenameValue] = useState('')
  const [notice, setNotice] = useState('')
  const [revisions, setRevisions] = useState<Revisions | null>(null)
  const [backup, setBackup] = useState<BackupState | null>(null)
  const [config, setConfig] = useState<BackupConfig>({ automatic: false, interval_hours: 24, keep_last: 3 })
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [confirmation, setConfirmation] = useState('')
  const request = useRequest()
  const actions = useRequest()
  const { run, cancel } = request
  function load(signal: AbortSignal) {
    return Promise.all([
      api<Revisions>('/workspace/revisions', { signal }),
      api<BackupState>('/workspace/backups', { signal }),
    ])
  }
  function loaded([nextRevisions, nextBackup]: [Revisions, BackupState]) {
    setRevisions(nextRevisions); setBackup(nextBackup); setConfig(nextBackup.settings)
  }
  useEffect(() => {
    if (!active) return
    void run(load, loaded)
    return cancel
  }, [active, run, cancel])
  const refresh = () => {
    request.cancel()
    void request.run(load, loaded)
  }
  const updatedProjects = () => {
    window.dispatchEvent(new Event('mboa:projects-updated'))
    setProjectName(''); setRenaming(''); setNotice('Project saved.')
    refresh()
  }
  return <section className="page workspace-settings" aria-labelledby="settings-title">
    <div className="page-intro"><div><div className="eyebrow">WORKSPACE MANAGEMENT</div><h1 id="settings-title">Workspace settings</h1><p>Manage your account, projects, recovery and private backups.</p></div>
      <button className="button button-secondary" type="button" onClick={refresh} disabled={request.pending}>Refresh settings</button></div>
    <ErrorNotice message={request.error || actions.error} />
    {notice && <p className="notice notice-success" role="status">{notice}</p>}
    {request.pending && <Spinner label="Loading workspace settings" />}
    {account && <section className="workspace-section"><h2>Your account</h2><p>{account.email} · Verified email</p>
      <label>Display name<input value={displayName} maxLength={100} onChange={(event) => setDisplayName(event.target.value)} /></label>
      <div className="workspace-actions">
        <button className="button button-secondary" type="button" disabled={actions.pending || !displayName.trim()} onClick={() => {
          void actions.run((signal) => api<Session>('/auth/profile', { method: 'PATCH', body: { display_name: displayName }, signal }), (next) => {
            onProfileChanged?.(next)
            setNotice('Your display name was updated.')
          })
        }}>Update name</button>
        <button className="button button-secondary" type="button" disabled={actions.pending} onClick={() => {
          void actions.run((signal) => api<{ message: string }>('/auth/forgot-password', { method: 'POST', body: { email: account.email }, signal }), (value) => setNotice(value.message))
        }}>Email password reset</button>
        {googleEnabled && !account.google_linked && <a className="button button-secondary" href="/api/auth/google/start?link=true">Link Google account</a>}
        {account.google_linked && <span>Google account linked</span>}
      </div>
    </section>}
    <section className="workspace-section"><h2>Projects</h2><p>Each project has its own collection, grammar, coursework profile, screenshots, recordings and legacy history. All projects belong only to your account.</p>
      {selectedProject !== 'default' && <p className="helper-text">Switch to another project before deleting the active project.</p>}
      <label>New project name<input value={projectName} maxLength={100} onChange={(event) => setProjectName(event.target.value)} /></label>
      <button className="button button-primary" type="button" disabled={actions.pending || !projectName.trim()} onClick={() => {
        void actions.run((signal) => api('/workspace/projects', { method: 'POST', body: { name: projectName }, signal }), updatedProjects)
      }}>Create project</button>
      {projects.map((project) => <div className="workspace-row" key={project.id}>
        {renaming === project.id ? <label>Project name<input value={renameValue} maxLength={100} onChange={(event) => setRenameValue(event.target.value)} /></label> : <strong>{project.name}</strong>}
        <div className="workspace-actions"><button className="button button-secondary" type="button" disabled={actions.pending} onClick={() => {
          if (renaming !== project.id) { setRenaming(project.id); setRenameValue(project.name); return }
          void actions.run((signal) => api(`/workspace/projects/${project.id}`, { method: 'PATCH', body: { name: renameValue }, signal }), updatedProjects)
        }}>{renaming === project.id ? 'Save project name' : 'Rename project'}</button>
          {project.id !== 'default' && <button className="button button-secondary" type="button" disabled={actions.pending || project.id === selectedProject} onClick={() => {
            if (!window.confirm(`Delete "${project.name}"? Only projects without collection records, saved history or coursework evidence can be deleted.`)) return
            void actions.run((signal) => api(`/workspace/projects/${project.id}`, { method: 'DELETE', signal }), () => { updatedProjects(); setNotice('Empty project deleted.') })
          }}>Delete empty project</button>}
        </div></div>)}
    </section>
    <section className="workspace-section"><h2>Change history and recovery</h2>
      <p>Latest 200 collection revisions in the selected project. Restoring a revision records another change and marks the entry unreviewed.</p>
      {revisions?.revisions.length === 0 && <p>No collection changes in this project yet.</p>}
      {revisions?.revisions.map((revision) => <div className="workspace-row" key={revision.id}>
        <div><strong>{revision.data.text}</strong><p>{revision.action} · {new Date(revision.timestamp).toLocaleString()}</p><p>{revision.data.french_gloss || revision.data.english_gloss}</p></div>
        <button type="button" className="button button-secondary" disabled={actions.pending} onClick={() => {
          if (!window.confirm('Restore this collection version? It may replace the current version. The restored entry will need review.')) return
          void actions.run((signal) => api(`/workspace/revisions/${revision.id}/restore`, {
            method: 'POST', body: { expected_version: revisions.workspace_version }, signal,
          }), () => { setNotice('Revision restored as unreviewed. Refresh Collection to review it.'); refresh() })
        }}>Restore revision</button>
      </div>)}
    </section>
    <section className="workspace-section"><h2>Private backups</h2>
      <p>Backups contain every project, collection revision, raw recording, legacy saved item, coursework profile and attached screenshot in your account, not your password or sessions. Saved grammars and report writing are included; unsaved browser drafts are not. Downloads contain private data: store them securely.</p>
      <div className="workspace-actions"><button type="button" className="button button-primary" disabled={actions.pending} onClick={() => {
        void actions.run((signal) => api('/workspace/backups', { method: 'POST', signal, timeout: 60000 }), () => { setNotice('Backup created and verified.'); refresh() })
      }}>Create verified backup</button></div>
      {backup?.backups.map((item) => <div className="workspace-row" key={item.id}><div><strong>{new Date(item.created_at).toLocaleString()}</strong><p>{item.kind} · {(item.size / 1024).toFixed(1)} KB</p></div>
        <div className="workspace-actions"><a className="button button-secondary" href={nativeApiUrl(`/workspace/backups/${item.id}/download`)}>Download backup</a>
          <button type="button" className="button button-secondary" disabled={actions.pending} onClick={() => {
            if (!window.confirm('Delete this server backup? Download it first if you need to keep it.')) return
            void actions.run((signal) => api(`/workspace/backups/${item.id}`, { method: 'DELETE', signal }), () => { setNotice('Backup deleted.'); refresh() })
          }}>Delete backup</button></div></div>)}
      <h3>Automatic backup schedule</h3>
      <label className="checkbox-label"><input type="checkbox" checked={config.automatic} onChange={(event) => setConfig({ ...config, automatic: event.target.checked })} />Enable automatic backups</label>
      <label>Backup frequency<select value={config.interval_hours} onChange={(event) => setConfig({ ...config, interval_hours: event.target.value === '168' ? 168 : 24 })}><option value="24">Daily</option><option value="168">Weekly</option></select></label>
      <label>Automatic backups to keep<input type="number" min={1} max={10} value={config.keep_last} onChange={(event) => setConfig({ ...config, keep_last: Number(event.target.value) })} /></label>
      <button className="button button-secondary" type="button" disabled={actions.pending || config.keep_last < 1 || config.keep_last > 10} onClick={() => {
        void actions.run((signal) => api('/workspace/backups/settings', { method: 'PATCH', body: config, signal }), () => { setNotice('Backup schedule saved. It runs while the application server is operating.'); refresh() })
      }}>Save backup schedule</button>
      <p className="helper-text">The server checks schedules every minute while running. Manual and pre-restore backups are not automatically pruned. Server-disk backups do not replace an off-server disaster-recovery copy.</p>
      {backup?.state.last_success && <p>Last automatic success: {new Date(backup.state.last_success * 1000).toLocaleString()}</p>}
      <ErrorNotice message={backup?.state.last_error ?? ''} />
      <h3>Restore a workspace backup</h3>
      <label>Backup ZIP (maximum 32 MB)<input type="file" accept=".zip" onChange={(event) => {
        setFile(event.target.files?.[0] ?? null); setPreview(null); setConfirmation(''); setNotice('')
      }} /></label>
      <button type="button" className="button button-secondary" disabled={actions.pending || !file} onClick={() => {
        if (!file) return
        const body = new FormData(); body.append('file', file)
        void actions.run((signal) => api<Preview>('/workspace/backups/preview', { method: 'POST', body, signal, timeout: 60000 }), setPreview)
      }}>Validate and preview backup</button>
      {preview && <div className="workspace-section"><h3>Restore preview</h3>
        <ul aria-label="Backup contents">{Object.entries(preview.counts).map(([key, count]) => <li key={key}>{count} {key === 'coursework' ? 'coursework profiles' : key === 'screenshots' ? 'coursework screenshots' : key}</li>)}</ul>
        <div aria-label="Restore warnings">{preview.warnings.map((warning) => <p className="notice notice-subtle" key={warning}>{warning}</p>)}</div>
        <p>Replacement includes project grammars, report writing and screenshot evidence. Read warnings about older backups: missing coursework is not reconstructed or inferred.</p>
        <label>Type REPLACE to confirm<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></label>
        <button type="button" className="button button-danger" disabled={actions.pending || confirmation !== 'REPLACE'} onClick={() => {
          void actions.run((signal) => api<{ pre_restore_backup_id: string }>('/workspace/backups/restore', {
            method: 'POST', body: { token: preview.token, expected_version: preview.workspace_version, confirmation: 'REPLACE' }, signal, timeout: 60000,
          }), () => window.dispatchEvent(new Event('mboa:workspace-restored')))
        }}>Replace my workspace</button>
      </div>}
    </section>
  </section>
}
