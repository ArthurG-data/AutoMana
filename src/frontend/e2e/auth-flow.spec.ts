// e2e/auth-flow.spec.ts
//
// End-to-end auth flow test covering signup, login, user menu, logout,
// and protected route redirection.  Requires both the frontend dev server
// (localhost:5173) and the FastAPI backend (localhost:8000) to be running.
//
// Architectural note:
//   UserMenu (avatar + "Login / Sign Up") lives in TopBar, which is rendered
//   by AppShell on /search and /cards/:id only.
//   The landing page (/) has its own inline nav with plain "Log in"/"Sign up"
//   buttons — it does NOT use TopBar or UserMenu.
//   So all UserMenu assertions navigate to /search first.
//
// Run with:  npx playwright test e2e/auth-flow.spec.ts

import { test, expect, type Page } from '@playwright/test'

// ──────────────────────────────────────────────────────────────────
//  Helpers
// ──────────────────────────────────────────────────────────────────

function makeTestUser() {
  const ts       = Date.now()
  const username = `playwright${ts}`
  const email    = `playwright${ts}@example.com`
  const password = 'Password123!'
  return { username, email, password }
}

async function createUserViaApi(opts: { username: string; email: string; password: string }) {
  const res = await fetch('http://localhost:8000/api/users/', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ username: opts.username, email: opts.email, password: opts.password }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(`Pre-condition failed — could not create user: ${res.status} ${JSON.stringify(body)}`)
  }
}

/** Log in via the UI and wait for the redirect to / (the landing page). */
async function loginViaUI(page: Page, email: string, password: string) {
  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('••••••••').fill(password)
  await page.getByRole('button', { name: /log in →/i }).click()
  await expect(page).toHaveURL('/', { timeout: 10_000 })
}

/**
 * Return the UserMenu avatar button.
 * Must be called on a page that renders AppShell (/search or /cards/:id).
 * The aria-label is "User menu for <username>".
 */
function avatarButton(page: Page, username: string) {
  return page.getByRole('button', { name: new RegExp(`user menu for ${username}`, 'i') })
}

/**
 * Return the "Login / Sign Up" button.
 * aria-label is "Log in or sign up" (accessible name takes priority over text).
 */
function loginSignupButton(page: Page) {
  return page.getByRole('button', { name: /log in or sign up/i })
}

/** Clear sessionStorage so the auth store has no persisted token. */
async function clearSession(page: Page) {
  // Navigate to a public page first so we can run JS
  await page.goto('/search')
  await page.evaluate(() => sessionStorage.clear())
  await page.reload()
}

// ──────────────────────────────────────────────────────────────────
//  Part 1 — Unauthenticated public access
// ──────────────────────────────────────────────────────────────────

test.describe('Part 1 — Unauthenticated public access', () => {
  test('/search loads and shows the filter sidebar', async ({ page }) => {
    await page.goto('/search')
    await expect(page.locator('aside')).toBeVisible({ timeout: 8_000 })
    await expect(page.getByText('Filters')).toBeVisible()
  })

  test('/cards/:id loads card detail without auth', async ({ page }) => {
    await page.goto('/search?q=ragavan')
    await expect(page.getByText('Ragavan, Nimble Pilferer').first()).toBeVisible({ timeout: 8_000 })
    await page.getByText('Ragavan, Nimble Pilferer').first().click()
    await expect(page).toHaveURL(/\/cards\//, { timeout: 8_000 })
    await expect(page.getByRole('heading', { name: 'Ragavan, Nimble Pilferer' }).first()).toBeVisible()
  })

  test('upper-right on /search shows "Login / Sign Up" when unauthenticated', async ({ page }) => {
    await clearSession(page)
    // After reload we're on /search (a public page) — TopBar + UserMenu are rendered
    await expect(loginSignupButton(page)).toBeVisible({ timeout: 8_000 })
  })
})

// ──────────────────────────────────────────────────────────────────
//  Part 2 — Sign up flow
// ──────────────────────────────────────────────────────────────────

test.describe('Part 2 — Sign up flow', () => {
  test('signup creates account, auto-logs in, and redirects to /', async ({ page }) => {
    const { username, email, password } = makeTestUser()

    await page.goto('/login')
    await page.getByRole('button', { name: 'Create one' }).click()
    await expect(page.getByText('Create account').first()).toBeVisible()

    await page.getByPlaceholder('yourname').fill(username)
    await page.getByPlaceholder('you@example.com').fill(email)
    await page.getByPlaceholder('••••••••').fill(password)
    await page.getByRole('button', { name: /create account/i }).click()

    // Should redirect to the landing page
    await expect(page).toHaveURL('/', { timeout: 10_000 })

    // Navigate to /search to verify the UserMenu shows the avatar (TopBar is on /search)
    await page.goto('/search')
    await expect(avatarButton(page, username)).toBeVisible({ timeout: 5_000 })
  })

  test('duplicate signup shows conflict error', async ({ page }) => {
    const { username, email, password } = makeTestUser()
    await createUserViaApi({ username, email, password })

    await page.goto('/login')
    await page.getByRole('button', { name: 'Create one' }).click()
    await page.getByPlaceholder('yourname').fill(username)
    await page.getByPlaceholder('you@example.com').fill(email)
    await page.getByPlaceholder('••••••••').fill(password)
    await page.getByRole('button', { name: /create account/i }).click()

    await expect(page.getByRole('alert')).toContainText(/already exists/i, { timeout: 8_000 })
    await expect(page).toHaveURL('/login')
  })
})

// ──────────────────────────────────────────────────────────────────
//  Part 3 — User menu and logout
// ──────────────────────────────────────────────────────────────────

test.describe('Part 3 — User menu and logout', () => {
  test('user menu shows username, email, and Log out button', async ({ page }) => {
    const { username, email, password } = makeTestUser()
    await createUserViaApi({ username, email, password })
    await loginViaUI(page, email, password)

    // Navigate to /search where TopBar + UserMenu live
    await page.goto('/search')
    await avatarButton(page, username).click()

    const menu = page.getByRole('menu', { name: 'User menu' })
    await expect(menu).toBeVisible()
    // Use exact match so the username text doesn't also match the email substring
    await expect(menu.getByText(username, { exact: true })).toBeVisible()
    await expect(menu.getByText(email, { exact: true })).toBeVisible()
    // Log out is a menuitem (role="menuitem") inside the dropdown
    await expect(menu.getByRole('menuitem', { name: /log out/i })).toBeVisible()
  })

  test('clicking Log out clears session and redirects to /search', async ({ page }) => {
    const { username, email, password } = makeTestUser()
    await createUserViaApi({ username, email, password })
    await loginViaUI(page, email, password)

    // Navigate to /search where the user menu lives
    await page.goto('/search')
    await avatarButton(page, username).click()
    // Log out is role="menuitem" inside the dropdown
    await page.getByRole('menuitem', { name: /log out/i }).click()

    // __root.tsx watches token → null and navigates to /search
    await expect(page).toHaveURL('/search', { timeout: 10_000 })
    // UserMenu should revert to "Login / Sign Up"
    await expect(loginSignupButton(page)).toBeVisible()
  })
})

// ──────────────────────────────────────────────────────────────────
//  Part 4 — Login flow (fresh session)
// ──────────────────────────────────────────────────────────────────

test.describe('Part 4 — Login flow (fresh session)', () => {
  test('valid credentials redirect to / then show avatar on /search', async ({ page }) => {
    const { username, email, password } = makeTestUser()
    await createUserViaApi({ username, email, password })

    await page.goto('/login')
    await expect(page.getByText('Log in').first()).toBeVisible()

    await page.getByPlaceholder('you@example.com').fill(email)
    await page.getByPlaceholder('••••••••').fill(password)
    await page.getByRole('button', { name: /log in →/i }).click()

    await expect(page).toHaveURL('/', { timeout: 10_000 })

    // Navigate to /search (where TopBar / UserMenu live) to verify auth state
    await page.goto('/search')
    await expect(avatarButton(page, username)).toBeVisible({ timeout: 5_000 })
  })

  test('invalid credentials shows inline error and stays on /login', async ({ page }) => {
    const { email } = makeTestUser() // Non-existent email
    await page.goto('/login')
    await page.getByPlaceholder('you@example.com').fill(email)
    await page.getByPlaceholder('••••••••').fill('WrongPassword999!')
    await page.getByRole('button', { name: /log in →/i }).click()

    await expect(page.getByRole('alert')).toContainText(/invalid email or password/i, { timeout: 8_000 })
    await expect(page).toHaveURL('/login')
  })
})

// ──────────────────────────────────────────────────────────────────
//  Part 5 — Protected routes
// ──────────────────────────────────────────────────────────────────

test.describe('Part 5 — Protected routes', () => {
  test('/ is accessible when logged in (landing page renders)', async ({ page }) => {
    const { username, email, password } = makeTestUser()
    await createUserViaApi({ username, email, password })
    await loginViaUI(page, email, password)

    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { name: /track every card/i })).toBeVisible()
  })

  test('unauthenticated visit to / redirects to /search', async ({ page }) => {
    await clearSession(page)
    await page.goto('/')
    // __root.tsx beforeLoad: unauthenticated / → redirect to /search
    await expect(page).toHaveURL('/search', { timeout: 5_000 })
  })

  test('unauthenticated visit to an unknown protected route redirects to /login', async ({ page }) => {
    await clearSession(page)
    await page.goto('/dashboard')
    await expect(page).toHaveURL('/login', { timeout: 5_000 })
  })

  test('[KNOWN GAP] /collection is not a registered route — unauthenticated redirects to /login', async ({ page }) => {
    // /collection appears in the task spec but has NOT been implemented.
    // It is absent from routeTree.gen.ts (only /, /login, /search, /cards/$id exist).
    // Unauthenticated: __root.tsx auth guard fires before route matching → /login.
    await clearSession(page)
    await page.goto('/collection')
    await expect(page).toHaveURL('/login', { timeout: 5_000 })
    // An authenticated visit would hit TanStack Router's not-found boundary.
  })
})
