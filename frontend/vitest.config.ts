import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/setup.ts'],
    maxWorkers: process.env.CI ? 2 : 4,
    testTimeout: 10000,
    clearMocks: true,
    restoreMocks: true,
    unstubGlobals: true,
  },
})
