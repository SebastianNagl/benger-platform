/**
 * Configuration Tests - Prevent production data leakage
 *
 * These tests validate that:
 * 1. Next.js rewrites are environment-aware
 * 2. Only one config file is active
 * 3. Development mode doesn't redirect to production
 */

import { existsSync, readFileSync } from 'fs'
import { join } from 'path'

describe('Next.js Configuration Security', () => {
  const configDir = join(process.cwd())

  test('should only have one active Next.js config file', () => {
    const configFiles = ['next.config.js', 'next.config.mjs', 'next.config.ts']

    const activeConfigs = configFiles.filter((file) =>
      existsSync(join(configDir, file))
    )

    // Should have exactly one config file
    expect(activeConfigs).toHaveLength(1)

    // Should not have .mjs file (lower priority than .js)
    expect(activeConfigs).not.toContain('next.config.mjs')
  })

  test('should not have production rewrites in development', () => {
    const configPath = join(configDir, 'next.config.js')

    if (existsSync(configPath)) {
      const configContent = readFileSync(configPath, 'utf-8')

      // Should not have hardcoded production URLs without environment checks
      if (configContent.includes('what-a-benger.net')) {
        // If production URLs exist, they must be behind environment checks
        expect(configContent).toMatch(/if.*NODE_ENV.*production/)
      }

      // Check for safe patterns: either empty rewrites or environment-aware rewrites
      const hasEmptyRewrites = configContent.includes('return []')
      const hasEnvironmentAwareRewrites =
        configContent.includes('NODE_ENV') &&
        configContent.includes('production')

      // Should have either empty rewrites (safe) or environment-aware rewrites
      expect(hasEmptyRewrites || hasEnvironmentAwareRewrites).toBe(true)

      // Should not have direct production URL without env check
      const hasDirectProductionUrl =
        /destination.*what-a-benger\.net/.test(configContent) &&
        !configContent.includes('NODE_ENV')
      expect(hasDirectProductionUrl).toBe(false)
    }
  })

  test('should have disabled .mjs config file if it exists', () => {
    const disabledConfigPath = join(configDir, 'next.config.mjs.disabled')
    const activeConfigPath = join(configDir, 'next.config.mjs')

    if (existsSync(disabledConfigPath)) {
      // If disabled version exists, active version should not
      expect(existsSync(activeConfigPath)).toBe(false)
    }
  })
})

describe('Environment Variable Configuration', () => {
  test('should have development environment set', () => {
    // In test environment, NODE_ENV should be 'test'
    // But we can check that development config is properly handled
    const isDevelopment = process.env.NODE_ENV !== 'production'
    expect(isDevelopment).toBe(true)
  })

  test('should not have production API URLs in development env vars', () => {
    const apiBaseUrl =
      process.env.REACT_APP_API_BASE_URL || process.env.API_BASE_URL

    if (apiBaseUrl && process.env.NODE_ENV !== 'production') {
      expect(apiBaseUrl).not.toMatch(/what-a-benger\.net/)
      expect(apiBaseUrl).not.toMatch(/https:\/\/api\./)
    }
  })
})
