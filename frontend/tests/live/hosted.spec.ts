import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { readFile, readdir } from 'node:fs/promises'
import { join } from 'node:path'
import { randomUUID } from 'node:crypto'

const password = 'Live-browser-test-passphrase-2026!'

async function emailLink(email: string, kind: string): Promise<string> {
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

async function signUp(page: Page): Promise<string> {
  const email = `test-${randomUUID()}@example.com`
  await page.goto('/#register')
  await page.getByLabel('Your name', { exact: true }).fill('Synthetic business user')
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel(/^Password/).fill(password)
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('verification link')
  await page.goto(await emailLink(email, 'verify-email'))
  await page.getByRole('button', { name: 'Verify email', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
  await page.getByLabel('Email address').fill(email)
  await page.getByLabel(/^Password/).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
  return email
}

async function addEntry(page: Page, text: string) {
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Terminology', exact: true }).click()
  await page.getByRole('button', { name: 'Add entry', exact: true }).click()
  const editor = page.getByRole('dialog', { name: 'Add terminology' })
  await editor.getByRole('textbox', { name: /^Expression/ }).fill(text)
  await editor.getByRole('button', { name: 'Save unreviewed' }).click()
  await expect(editor).not.toBeVisible()
  await expect(page.getByRole('heading', { name: text, exact: true })).toBeVisible()
}

test.beforeEach(async ({ context }) => {
  await context.route(/^https?:\/\/(?!127\.0\.0\.1:4190\/).*/, (route) => route.abort('blockedbyclient'))
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
      getUserMedia: () => Promise.reject(new Error('Physical hardware is not used in automated tests.')),
    } })
  })
})

test('real registration, verification, private data, sessions and reload persistence', async ({ page, browser }) => {
  await signUp(page)
  await addEntry(page, 'Synthetic customer greeting')
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Synthetic customer greeting', exact: true })).toBeVisible()
  const otherContext = await browser.newContext({ baseURL: 'http://127.0.0.1:4190' })
  try {
    const other = await otherContext.newPage()
    await signUp(other)
    await other.goto('/#collection')
    await expect(other.getByRole('heading', { name: 'Build your terminology library' })).toBeVisible()
    await expect(other.getByRole('heading', { name: 'Synthetic customer greeting', exact: true })).toHaveCount(0)
  } finally {
    await otherContext.close()
  }
  const sharedTab = await page.context().newPage()
  try {
    await sharedTab.goto('/#collection')
    await expect(sharedTab.getByRole('heading', { name: 'Synthetic customer greeting', exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.cookie)).not.toContain('mboa_session')
    page.once('dialog', (dialog) => dialog.accept())
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
    await expect(sharedTab.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
    await expect(page.getByText('Synthetic customer greeting', { exact: true })).toHaveCount(0)
    await expect(sharedTab.getByText('Synthetic customer greeting', { exact: true })).toHaveCount(0)
  } finally {
    await sharedTab.close()
  }
})

test('saved translation, projects, revision recovery and verified backup restoration', async ({ page }) => {
  await signUp(page)
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  await navigation.getByRole('link', { name: 'Dictionary', exact: true }).click()
  await page.getByRole('searchbox').fill('tchop')
  await page.getByRole('button', { name: 'Open tchop in translator', exact: true }).click()
  await page.getByRole('button', { name: 'Translate', exact: true }).click()
  await expect(page.getByText('to eat', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Save translation', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Saved to history' })).toBeVisible()
  await navigation.getByRole('link', { name: 'History', exact: true }).click()
  await page.getByRole('button', { name: 'Open tchop', exact: true }).click()
  await expect(page.getByLabel('Saved work details')).toContainText('to eat')
  await addEntry(page, 'Synthetic recoverable term')
  await page.getByRole('button', { name: 'Delete expression: Synthetic recoverable term' }).click()
  await page.getByRole('button', { name: 'Yes, remove it' }).click()
  await navigation.getByRole('link', { name: 'Workspace settings', exact: true }).click()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Restore revision', exact: true }).first().click()
  await expect(page.getByRole('status').filter({ hasText: 'Revision restored as unreviewed' })).toBeVisible()
  await page.getByRole('button', { name: 'Create verified backup' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Backup created and verified' })).toBeVisible()
  const downloaded = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Download backup' }).first().click()
  const download = await downloaded
  const path = await download.path()
  if (!path) throw new Error('Expected a real private backup download.')
  await addEntry(page, 'Synthetic post-backup term')
  await navigation.getByRole('link', { name: 'Workspace settings', exact: true }).click()
  await page.getByLabel('Backup ZIP (maximum 32 MB)').setInputFiles(path)
  await page.getByRole('button', { name: 'Validate and preview backup' }).click()
  await expect(page.getByRole('heading', { name: 'Restore preview', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Replace my workspace' })).toBeDisabled()
  await page.getByLabel('Type REPLACE to confirm').fill('REPLACE')
  await page.getByRole('button', { name: 'Replace my workspace' }).click()
  await expect(page.getByText('Workspace restored. Review the restored information before using it.')).toBeVisible()
  await navigation.getByRole('link', { name: 'Terminology', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Synthetic recoverable term', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Synthetic post-backup term', exact: true })).toHaveCount(0)
  await navigation.getByRole('link', { name: 'Workspace settings', exact: true }).click()
  await page.getByLabel('New project name').fill('Synthetic client project')
  await page.getByRole('button', { name: 'Create project', exact: true }).click()
  await expect(page.getByLabel('Active project')).toContainText('Synthetic client project')
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByLabel('Active project').selectOption({ label: 'Synthetic client project' })
  await navigation.getByRole('link', { name: 'Terminology', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Build your terminology library' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('real password recovery revokes existing sessions and replaces the old password', async ({ page, browser }) => {
  const email = await signUp(page)
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Workspace settings', exact: true }).click()
  await page.getByRole('button', { name: 'Email password reset', exact: true }).click()
  await expect(page.getByRole('status').filter({ hasText: 'reset link' })).toBeVisible()
  const recoveryContext = await browser.newContext({ baseURL: 'http://127.0.0.1:4190' })
  try {
    const recovery = await recoveryContext.newPage()
    await recovery.goto(await emailLink(email, 'reset-password'))
    const replacement = 'Replacement-live-test-passphrase-2026!'
    await recovery.getByLabel(/^Password/).fill(replacement)
    await recovery.getByRole('button', { name: 'Update password', exact: true }).click()
    await expect(recovery.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Sign in to Mboa' })).toBeVisible()
    await recovery.getByLabel('Email address').fill(email)
    await recovery.getByLabel(/^Password/).fill(password)
    await recovery.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(recovery.getByRole('alert')).toContainText('email or password is incorrect')
    await recovery.getByLabel(/^Password/).fill(replacement)
    await recovery.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(recovery.getByRole('navigation', { name: 'Main navigation' })).toBeVisible()
  } finally {
    await recoveryContext.close()
  }
})
