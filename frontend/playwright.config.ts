import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const origin = 'http://127.0.0.1:4187'
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm'
const stagedAssets = process.env.MBOA_E2E_DIST_DIR

export default defineConfig({
  testDir: join('tests', 'e2e'),
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : 4,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: origin,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    serviceWorkers: 'block',
    permissions: [],
    launchOptions: { downloadsPath: fileURLToPath(new URL('.playwright/downloads', import.meta.url)) },
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: `${npm} run preview -- --host 127.0.0.1 --port 4187 --strictPort${stagedAssets ? ` --outDir "${stagedAssets}"` : ''}`,
    cwd: fileURLToPath(new URL('.', import.meta.url)),
    url: origin,
    reuseExistingServer: false,
    timeout: 30000,
  },
})
