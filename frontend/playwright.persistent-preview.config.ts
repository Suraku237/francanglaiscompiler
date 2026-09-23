import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({
  ...base,
  outputDir: '.playwright/persistent-analysis-results',
  reporter: [['list']],
  webServer: {
    ...base.webServer,
    command: 'npm run preview -- --outDir .playwright\\persistent-analysis-build --host 127.0.0.1 --port 4187 --strictPort',
  },
})
