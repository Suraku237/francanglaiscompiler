import { expect } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const silence = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'fixtures', 'imports', 'silence.wav')

export async function playMuted(player: Locator) {
  await player.evaluate(async (element) => {
    if (!(element instanceof HTMLAudioElement)) throw new Error('Expected the actual audio player.')
    element.muted = true
    await element.play()
  })
  await expect.poll(() => player.evaluate((element) => {
    if (!(element instanceof HTMLAudioElement)) throw new Error('Expected the actual audio player.')
    if (element.error) throw new Error(`Audio decoding failed: ${element.error.message}`)
    return element.currentTime
  })).toBeGreaterThan(0)
}

export async function downloadedBytes(page: Page, link: Locator): Promise<Buffer> {
  const pending = page.waitForEvent('download')
  await link.click()
  const download = await pending
  const path = await download.path()
  if (!path) throw new Error('Expected a real browser audio download.')
  return readFile(path)
}
