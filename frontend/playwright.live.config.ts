import { defineConfig, devices } from '@playwright/test'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = fileURLToPath(new URL('.', import.meta.url))
const origin = 'http://127.0.0.1:4190'

export default defineConfig({
  testDir: join('tests', 'live'),
  fullyParallel: false,
  workers: 1,
  timeout: 90000,
  expect: { timeout: 15000 },
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: 'playwright-live-report', open: 'never' }]],
  use: { baseURL: origin, trace: 'retain-on-failure', screenshot: 'only-on-failure', serviceWorkers: 'block',
    actionTimeout: 15000,
    launchOptions: { downloadsPath: join(frontend, '.playwright', 'downloads') } },
  projects: [
    { name: 'live-chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'live-mobile', use: { ...devices['Pixel 7'] } },
  ],
})
