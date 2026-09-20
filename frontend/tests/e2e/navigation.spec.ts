import { test, expect } from './fixtures'
import { health } from '../fixtures'

test('hash navigation, browser history and the skip link keep the active page and focus aligned', async ({ page }) => {
  await page.goto('/#unknown-page')
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(navigation.getByRole('link', { name: 'Translate', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page).toHaveTitle('Translate — Mboa Workspace')
  await page.getByRole('textbox', { name: 'French text to translate' }).fill('Tab-only draft')

  await navigation.getByRole('link', { name: 'Terminology', exact: true }).click()
  await expect(page).toHaveURL(/#collection$/)
  await expect(page).toHaveTitle('Terminology — Mboa Workspace')
  await expect(page.getByRole('main')).toBeFocused()
  await expect(page.getByRole('button', { name: 'Add entry', exact: true })).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'French text to translate' })).not.toBeVisible()

  await page.goBack()
  await expect(page).toHaveTitle('Translate — Mboa Workspace')
  await expect(page.getByRole('textbox', { name: 'French text to translate' })).toHaveValue('Tab-only draft')
  await expect(page.getByRole('main')).toBeFocused()
  await page.getByRole('link', { name: 'Skip to content' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()
  await expect(page).toHaveURL(/#translator$/)
})

test('native privacy dialog traps keyboard focus, closes with Escape and restores its trigger', async ({ page, isMobile }) => {
  await page.goto('/')
  const trigger = isMobile
    ? page.getByRole('button', { name: 'Workspace settings and privacy' })
    : page.getByRole('button', { name: 'Settings & privacy' })
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: 'Workspace settings & privacy' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Close dialog' })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(dialog.getByRole('button', { name: 'Done', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(dialog.getByRole('button', { name: 'Close dialog' })).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
})

test('backend recovery enables AI only after a successful health check without sending a draft', async ({ page, api }) => {
  api.reply('GET', '/api/health', { detail: 'Fixture backend temporarily unavailable.' }, 503)
  await page.goto('/')
  await expect(page.getByText('Backend offline', { exact: true })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: 'Allow AI suggestions for gaps' })).toBeDisabled()
  await page.getByRole('textbox', { name: 'French text to translate' }).fill('Draft while offline')
  api.reply('GET', '/api/health', health(true))
  await page.getByRole('button', { name: 'Check backend connection' }).click()
  await expect(page.getByText('AI configured', { exact: true })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: 'Allow AI suggestions for gaps' })).toBeEnabled()
  await expect(page.getByRole('textbox', { name: 'French text to translate' })).toHaveValue('Draft while offline')
  expect(api.calls('/api/translate')).toHaveLength(0)
})
