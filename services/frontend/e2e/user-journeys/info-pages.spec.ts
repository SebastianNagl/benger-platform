/**
 * E2E tests for informational/static pages
 * Tests that public-facing info pages load correctly and display expected content.
 * These pages are accessible after login and render translated content.
 */

import { expect, Page, test } from '@playwright/test'
import { TestHelpers } from '../helpers/test-helpers'

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || ''

test.describe('Info Pages', () => {
  let page: Page
  let helpers: TestHelpers

  test.beforeEach(async ({ page: testPage }) => {
    page = testPage
    helpers = new TestHelpers(page)
    await page.setViewportSize({ width: 1920, height: 1080 })
    await helpers.login('admin', 'admin')
  })

  test('imprint page loads with legal content', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/about/imprint`, { timeout: 30000 })

    // Verify the page heading (EN or DE)
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })
    await expect(async () => {
      const text = await heading.textContent()
      const hasTitle =
        text?.includes('Imprint') || text?.includes('Impressum')
      expect(hasTitle).toBe(true)
    }).toPass({ timeout: 15000 })

    // Verify legal content sections exist (provider info, contact, etc.)
    await expect(async () => {
      const bodyText = await page.locator('main, article, body').first().textContent()
      const hasLegalContent =
        bodyText?.includes('Contact') ||
        bodyText?.includes('Kontakt') ||
        bodyText?.includes('Disclaimer') ||
        bodyText?.includes('Haftungsausschluss') ||
        bodyText?.includes('Provider') ||
        bodyText?.includes('Anbieter')
      expect(hasLegalContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('data protection page loads with privacy content', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/about/data-protection`, { timeout: 30000 })

    // Verify the page heading
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })
    await expect(async () => {
      const text = await heading.textContent()
      const hasTitle =
        text?.includes('Data Protection') ||
        text?.includes('Datenschutz') ||
        text?.includes('Privacy')
      expect(hasTitle).toBe(true)
    }).toPass({ timeout: 15000 })

    // Verify privacy-related content sections
    await expect(async () => {
      const bodyText = await page.locator('main, article, body').first().textContent()
      const hasPrivacyContent =
        bodyText?.includes('Data') ||
        bodyText?.includes('Daten') ||
        bodyText?.includes('Cookies') ||
        bodyText?.includes('Rights') ||
        bodyText?.includes('Rechte')
      expect(hasPrivacyContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('how-to page loads with guide content', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/how-to`, { timeout: 30000 })

    // Verify the page heading
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })
    await expect(async () => {
      const text = await heading.textContent()
      const hasTitle =
        text?.includes('How') ||
        text?.includes('Anleitung') ||
        text?.includes('Guide') ||
        text?.includes('Leitfaden')
      expect(hasTitle).toBe(true)
    }).toPass({ timeout: 15000 })

    // Verify guide sections exist (workflow steps)
    await expect(async () => {
      const bodyText = await page.locator('body').textContent()
      const hasGuideContent =
        bodyText?.includes('Platform') ||
        bodyText?.includes('Plattform') ||
        bodyText?.includes('Workflow') ||
        bodyText?.includes('Annotation') ||
        bodyText?.includes('Project') ||
        bodyText?.includes('Projekt')
      expect(hasGuideContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('models page loads and shows model list or loading state', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/models`, { timeout: 30000 })

    // The models page fetches data from API and shows a model catalog
    // Verify the page renders meaningful content
    await expect(async () => {
      const bodyText = await page.locator('body').textContent()
      const hasModelContent =
        bodyText?.includes('Model') ||
        bodyText?.includes('Modell') ||
        bodyText?.includes('Provider') ||
        bodyText?.includes('Anbieter') ||
        bodyText?.includes('OpenAI') ||
        bodyText?.includes('Anthropic') ||
        bodyText?.includes('LLM') ||
        bodyText?.includes('Loading') ||
        bodyText?.includes('Laden')
      expect(hasModelContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('architecture page loads with system documentation', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/architecture`, { timeout: 30000 })

    // Verify the page heading
    const heading = page.locator('h1').first()
    await expect(heading).toBeVisible({ timeout: 30000 })
    await expect(async () => {
      const text = await heading.textContent()
      const hasTitle =
        text?.includes('Architecture') ||
        text?.includes('Architektur')
      expect(hasTitle).toBe(true)
    }).toPass({ timeout: 15000 })

    // Verify architecture sections exist (overview, frontend, api, etc.)
    await expect(async () => {
      const bodyText = await page.locator('body').textContent()
      const hasArchitectureContent =
        bodyText?.includes('Frontend') ||
        bodyText?.includes('API') ||
        bodyText?.includes('Database') ||
        bodyText?.includes('Datenbank') ||
        bodyText?.includes('Celery') ||
        bodyText?.includes('Worker')
      expect(hasArchitectureContent).toBe(true)
    }).toPass({ timeout: 15000 })
  })

  test('about page redirects to home', async () => {
    test.setTimeout(60000)

    await page.goto(`${BASE_URL}/about`, { timeout: 30000 })

    // The /about page redirects to / (home)
    await expect(async () => {
      const url = page.url()
      // Should have been redirected away from /about
      // Could end up at /, /dashboard, /projects, or /login
      const isRedirected =
        !url.endsWith('/about') ||
        url.includes('/dashboard') ||
        url.includes('/login')
      expect(isRedirected).toBe(true)
    }).toPass({ timeout: 15000 })
  })
})
