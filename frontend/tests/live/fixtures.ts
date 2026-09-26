import { expect, test as base } from '@playwright/test'
import { execFileSync, spawn } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { setTimeout } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'
import type { EditableEntry } from '../../src/types'

const frontend = fileURLToPath(new URL('../..', import.meta.url))
const root = resolve(frontend, '..')
const fixtureRoot = join(frontend, '.playwright')
const origin = 'http://127.0.0.1:4190'

export interface LiveSeed {
  corpus?: 'yaounde'
  grammar?: string
  entries?: (Partial<EditableEntry> & { text: string; audio?: boolean })[]
  readings?: { text: string; language: 'fr' | 'en' }[]
  tests?: { text: string; grammar: string }[]
}

export function seedLiveData(seed: LiveSeed): { entry_ids: string[]; reading_ids: string[]; test_ids: string[] } {
  const data = process.env.MBOA_LIVE_DATA_DIR
  if (!data) throw new Error('Missing explicit isolated browser fixture directory.')
  const python = process.platform === 'win32' ? join(root, '.venv', 'Scripts', 'python.exe') : 'python'
  return JSON.parse(execFileSync(python, [join(frontend, 'tests', 'live', 'seed_data.py'), data], {
    cwd: root, input: JSON.stringify(seed), encoding: 'utf8', timeout: 30000,
    env: { ...process.env, MBOA_DATA_DIR: data, TEMP: fixtureRoot, TMP: fixtureRoot, TMPDIR: fixtureRoot },
  }))
}

export { expect }
export const test = base.extend<{ liveServer: void; seed: LiveSeed }>({
  seed: [{}, { option: true }],
  liveServer: [async ({ request, seed }, use, testInfo) => {
    mkdirSync(fixtureRoot, { recursive: true })
    const data = mkdtempSync(join(fixtureRoot, 'mboa-live-'))
    const previousData = process.env.MBOA_LIVE_DATA_DIR
    process.env.MBOA_LIVE_DATA_DIR = data
    const python = process.platform === 'win32' ? join(root, '.venv', 'Scripts', 'python.exe') : 'python'
    const args = ['-m', 'tools.live_test_server', '--data-dir', data, '--port', '4190', '--stop-on-stdin']
    if (process.env.MBOA_LIVE_FRONTEND_DIR) {
      args.push('--frontend-dir', resolve(frontend, process.env.MBOA_LIVE_FRONTEND_DIR))
    }
    const server = spawn(python, args, { cwd: root, stdio: ['pipe', 'pipe', 'pipe'], env: {
      ...process.env, TEMP: fixtureRoot, TMP: fixtureRoot, TMPDIR: fixtureRoot,
      MBOA_PUBLIC_URL: origin, MBOA_ENVIRONMENT: 'development', MBOA_MAIL_MODE: 'file',
      MBOA_DATA_DIR: data, MBOA_GOOGLE_CLIENT_ID: '', MBOA_GOOGLE_CLIENT_SECRET: '',
    } })
    let log = ''
    let exitError: Error | undefined
    server.stdout.on('data', (chunk: Buffer) => { log += chunk.toString() })
    server.stderr.on('data', (chunk: Buffer) => { log += chunk.toString() })
    const stopped = new Promise<void>((done) => {
      server.once('error', (error) => { exitError = error; done() })
      server.once('exit', (code, signal) => {
        if (code !== 0) exitError = new Error(`Live server exited with code ${code}, signal ${signal}.`)
        done()
      })
    })
    try {
      await Promise.race([
        expect(async () => {
          const health = await request.get('/api/health', { timeout: 1000 })
          expect(health.status()).toBe(200)
          expect(await health.json()).toMatchObject({ status: 'ok', mode: 'compiler' })
        }).toPass({ timeout: 30000, intervals: [100, 200, 500] }),
        stopped.then(() => { throw new Error(`Live server stopped before becoming ready.\n${exitError?.message ?? ''}\n${log}`) }),
      ])
      if (Object.keys(seed).length) {
        const initialized = await request.get('/api/analyzer')
        expect(initialized.status(), await initialized.text()).toBe(200)
        seedLiveData(seed)
      }
      await use()
    } finally {
      if (server.pid && server.exitCode === null && server.signalCode === null) server.stdin.end()
      const timedOut = await Promise.race([stopped.then(() => false), setTimeout(10000, true, { ref: false })])
      if (timedOut && server.pid) {
        if (process.platform === 'win32') {
          execFileSync('powershell.exe', ['-NoProfile', '-Command', `Stop-Process -Id ${server.pid} -ErrorAction Stop`])
        } else {
          server.kill('SIGKILL')
        }
        await stopped
        exitError = new Error('The isolated live server did not shut down gracefully.')
      }
      writeFileSync(testInfo.outputPath('server.log'), log)
      rmSync(data, { recursive: true, force: true })
      if (previousData === undefined) delete process.env.MBOA_LIVE_DATA_DIR
      else process.env.MBOA_LIVE_DATA_DIR = previousData
      if (exitError) throw exitError
    }
  }, { auto: true, timeout: 45000 }],
})
