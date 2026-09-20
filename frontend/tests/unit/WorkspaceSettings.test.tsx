import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { WorkspaceSettings } from '../../src/WorkspaceSettings'
import { deferred, jsonResponse } from '../helpers'

const projects = [
  { id: 'default', name: 'General', created_at: '2026-01-01T00:00:00Z' },
  { id: 'client-project', name: 'Client project', created_at: '2026-01-01T00:00:00Z' },
]

describe('project management', () => {
  it('requires switching away before deleting the active project', async () => {
    vi.mocked(fetch).mockImplementation(async (url) => {
      if (url === '/api/workspace/revisions') return jsonResponse({ revisions: [], workspace_version: 0 })
      if (url === '/api/workspace/backups') return jsonResponse({
        backups: [], settings: { automatic: false, interval_hours: 24, keep_last: 3 },
        state: {}, workspace_version: 0,
      })
      throw new Error(`Unexpected request: ${String(url)}`)
    })
    const { rerender } = render(<WorkspaceSettings active projects={projects} selectedProject="client-project" />)
    await screen.findByText('No terminology changes in this project yet.')
    expect(screen.getByRole('button', { name: 'Delete empty project' })).toBeDisabled()
    expect(screen.getByText('Switch to another project before deleting the active project.')).toBeVisible()
    rerender(<WorkspaceSettings active projects={projects} selectedProject="default" />)
    expect(screen.getByRole('button', { name: 'Delete empty project' })).toBeEnabled()
  })

  it('refreshes a newly created backup even when an older settings read is pending', async () => {
    const oldRead = deferred<Response>()
    const base = {
      settings: { automatic: false, interval_hours: 24, keep_last: 3 },
      state: {}, workspace_version: 0,
    }
    let reads = 0
    vi.mocked(fetch).mockImplementation(async (url, options) => {
      if (url === '/api/workspace/revisions') return jsonResponse({ revisions: [], workspace_version: 0 })
      if (url === '/api/workspace/backups' && options?.method === 'POST') return jsonResponse({ id: 'new-backup' }, 201)
      if (url === '/api/workspace/backups') {
        reads++
        if (reads === 1) return oldRead.promise
        return jsonResponse({ ...base, backups: [{ id: 'new-backup', kind: 'manual', created_at: '2026-01-01T00:00:00Z', size: 1024 }] })
      }
      throw new Error(`Unexpected request: ${String(url)}`)
    })
    const user = userEvent.setup()
    render(<WorkspaceSettings active projects={projects} selectedProject="default" />)
    await waitFor(() => expect(reads).toBe(1))
    await user.click(screen.getByRole('button', { name: 'Create verified backup' }))
    expect(await screen.findByRole('link', { name: 'Download backup' })).toHaveAttribute('href', '/api/workspace/backups/new-backup/download')
    await act(async () => oldRead.resolve(jsonResponse({ ...base, backups: [] })))
    expect(screen.getByRole('link', { name: 'Download backup' })).toBeVisible()
  })
})
