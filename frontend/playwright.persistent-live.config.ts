import { defineConfig } from '@playwright/test'
import base from './playwright.live.config'

const server = base.webServer
if (!server || Array.isArray(server)) throw new Error('Expected one isolated live-test server.')

export default defineConfig({
  ...base,
  outputDir: '.playwright/persistent-analysis-live-results',
  reporter: [['list']],
  webServer: {
    ...server,
    command: server.command.replace('tools.live_test_server', 'tools._persistent_analysis_live_server'),
  },
})
