// src/frontend/e2e/landing.spec.ts
import { test, expect } from '@playwright/test'

test('landing page loads and shows headline', async ({ page }) => {
  await page.goto('/')
  // The landing page h1 says "Track every card." (with a period)
  await expect(page.getByRole('heading', { name: /track every card/i })).toBeVisible()
  await expect(page.getByPlaceholder(/search any card/i)).toBeVisible()
})

test('quick search pill navigates to search page', async ({ page }) => {
  await page.goto('/')
  await page.getByText('Ragavan, Nimble Pilferer').click()
  await expect(page).toHaveURL(/\/search/)
})
