import { defineConfig, devices } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { randomUUID } from 'node:crypto'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const frontend = fileURLToPath(new URL('.', import.meta.url))
const fixtureRoot = join(frontend, '.playwright')
const data = process.env.MBOA_LIVE_DATA_DIR || join(fixtureRoot, `mboa-live-${randomUUID()}`)
mkdirSync(data, { recursive: true })
process.env.MBOA_LIVE_DATA_DIR = data
const origin = 'http://127.0.0.1:4190'
const python = process.platform === 'win32'
  ? `"${join(root, '.venv', 'Scripts', 'python.exe')}"`
  : 'python'

export default defineConfig({
  testDir: join('tests', 'live'),
  fullyParallel: false,
  workers: 1,
  timeout: 90000,
  expect: { timeout: 15000 },
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'playwright-live-report', open: 'never' }]],
  use: { baseURL: origin, trace: 'retain-on-failure', screenshot: 'only-on-failure', serviceWorkers: 'block',
    launchOptions: { downloadsPath: join(frontend, '.playwright', 'downloads') } },
  projects: [
    { name: 'live-chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'live-mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: `${python} -m tools.live_test_server --data-dir "${resolve(data)}" --port 4190`,
    cwd: root, url: `${origin}/api/health`, timeout: 60000, reuseExistingServer: false,
    env: { TEMP: fixtureRoot, TMP: fixtureRoot, TMPDIR: fixtureRoot,
      MBOA_PUBLIC_URL: origin, MBOA_ENVIRONMENT: 'development',
      MBOA_MAIL_MODE: 'file', MBOA_DATA_DIR: data, MBOA_GOOGLE_CLIENT_ID: '', MBOA_GOOGLE_CLIENT_SECRET: '' },
  },
})
