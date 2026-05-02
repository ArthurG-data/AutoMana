// src/frontend/e2e/search-to-detail.spec.ts
import { test, expect } from '@playwright/test'

test('search for ragavan shows results', async ({ page }) => {
  await page.goto('/search?q=ragavan')
  await expect(page.getByText('Ragavan, Nimble Pilferer').first()).toBeVisible()
})

test('clicking a card navigates to detail page', async ({ page }) => {
  await page.goto('/search?q=ragavan')
  await page.getByText('Ragavan, Nimble Pilferer').first().click()
  await expect(page).toHaveURL(/\/cards\/ragavan-mh2/)
  // The detail page renders the card name in two <h1> elements (TopBar title + CardDetailView name).
  // Use .first() to avoid strict mode violation.
  await expect(page.getByRole('heading', { name: 'Ragavan, Nimble Pilferer' }).first()).toBeVisible()
})
