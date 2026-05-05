// src/frontend/e2e/login.spec.ts
import { test, expect } from '@playwright/test'

// Note: these tests run against the live dev server + backend.
// A healthy backend is required for auth requests to succeed.

test('login page loads with email field and Log in heading', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByText('Log in').first()).toBeVisible()
  await expect(page.getByPlaceholder('you@example.com')).toBeVisible()
})

test('toggling to signup mode shows username field and Create account heading', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: 'Create one' }).click()
  await expect(page.getByText('Create account').first()).toBeVisible()
  await expect(page.getByPlaceholder('yourname')).toBeVisible()
})

test('toggling back from signup to login hides username field', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: 'Create one' }).click()
  await page.getByRole('button', { name: 'Log in' }).click()
  await expect(page.getByText('Log in').first()).toBeVisible()
  await expect(page.getByPlaceholder('yourname')).not.toBeVisible()
})

test.skip('invalid credentials shows error message — requires live backend', async ({ page }) => {
  // Hits POST /api/users/auth/token against the real dev backend.
  // Run manually with the backend up: `npx playwright test e2e/login.spec.ts`
  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill('nobody@example.com')
  await page.getByPlaceholder('••••••••').fill('wrongpassword')
  await page.getByRole('button', { name: /log in/i }).click()
  await expect(page.getByRole('alert')).toContainText('Invalid email or password')
})

test.skip('successful login navigates to /', async ({ page }) => {
  // Requires a valid test account in the dev database.
  // Run manually: fill in real credentials below.
  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill('test@example.com')
  await page.getByPlaceholder('••••••••').fill('testpassword')
  await page.getByRole('button', { name: /log in/i }).click()
  await expect(page).toHaveURL('/')
})
