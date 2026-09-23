import { defineConfig } from '@playwright/test'
import { fileURLToPath } from 'node:url'
import config from './playwright.config'

export default defineConfig({
  ...config,
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4187 --strictPort --outDir .playwright\\analysis-page-check-a781c9e2',
    cwd: fileURLToPath(new URL('.', import.meta.url)),
    url: 'http://127.0.0.1:4187',
    reuseExistingServer: false,
    timeout: 30000,
  },
})
