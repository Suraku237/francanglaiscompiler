import { defineConfig } from 'vite'

// Native downloads can bypass browser routing; mocked tests must never proxy to a real API.
export default defineConfig({ preview: { proxy: {} } })
