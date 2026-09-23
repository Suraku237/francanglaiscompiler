import type { Page } from '@playwright/test'

export async function openGrammarSettings(page: Page) {
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Analysis', exact: true }).click()
  if (!await page.getByLabel('Context-free grammar').isVisible()) {
    await page.getByText('Grammar settings', { exact: true }).click()
  }
}
