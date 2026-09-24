import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'
import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'

export const password = 'Live-browser-test-passphrase-2026!'

export async function emailLink(email: string, kind: string): Promise<string> {
  const directory = process.env.MBOA_LIVE_DATA_DIR
  if (!directory) throw new Error('Missing isolated browser fixture directory.')
  const files = await readdir(join(directory, 'mail'))
  for (const name of files.reverse()) {
    const raw = await readFile(join(directory, 'mail', name), 'utf8')
    const text = raw.replace(/=\r?\n/g, '').replace(/=([0-9A-F]{2})/g, (_, hex: string) => String.fromCharCode(parseInt(hex, 16)))
    if (text.includes(`To: ${email}`)) {
      const match = text.match(new RegExp(`http://127\\.0\\.0\\.1:4190/#${kind}\\?token=[A-Za-z0-9_-]+`))
      if (match) return match[0]
    }
  }
  throw new Error('The test verification email was not delivered to the isolated outbox.')
}

export async function signIn(page: Page, email: string): Promise<void> {
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel(/^Password/).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
}

export async function signUp(page: Page): Promise<string> {
  const email = `test-${randomUUID()}@example.com`
  await page.goto('/#register')
  await page.getByLabel('Your name', { exact: true }).fill('Synthetic compiler user')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel(/^Password/).fill(password)
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('verification link')
  await page.goto(await emailLink(email, 'verify-email'))
  await page.getByRole('button', { name: 'Verify email', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to Camfranglais' })).toBeVisible()
  await signIn(page, email)
  return email
}
