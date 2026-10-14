/**
 * @jest-environment jsdom
 */

import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from 'next-themes'

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(), // deprecated
    removeListener: jest.fn(), // deprecated
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
})

describe('Issue #231: Button Selector Fix', () => {
  describe('LanguageSwitcher', () => {
    it('should render with data-testid attribute', () => {
      render(
        <div>
          <LanguageSwitcher />
        </div>,
      )

      const button = screen.getByTestId('language-switcher')
      expect(button).toBeInTheDocument()
      expect(button).toHaveAttribute('type', 'button')
      expect(button).toHaveAttribute('aria-label')
    })

    it('should have proper ARIA attributes', () => {
      render(
        <div>
          <LanguageSwitcher />
        </div>,
      )

      const button = screen.getByTestId('language-switcher')
      expect(button).toHaveAttribute('aria-label')
      expect(button.getAttribute('aria-label')).toMatch(
        /^Choose language: English$/,
      )
    })
  })

  describe('ThemeToggle', () => {
    it('should render with data-testid attribute', () => {
      render(
        <ThemeProvider attribute="class" defaultTheme="light">
          <ThemeToggle />
        </ThemeProvider>,
      )

      const button = screen.getByTestId('theme-toggle')
      expect(button).toBeInTheDocument()
      expect(button).toHaveAttribute('type', 'button')
      expect(button).toHaveAttribute('aria-label')
    })

    it('should have proper ARIA attributes', () => {
      render(
        <ThemeProvider attribute="class" defaultTheme="light">
          <ThemeToggle />
        </ThemeProvider>,
      )

      const button = screen.getByTestId('theme-toggle')
      expect(button).toHaveAttribute('aria-label')
      expect(button.getAttribute('aria-label')).toMatch(
        /^Switch to (dark|light) theme$/,
      )
    })
  })
})

// Catalog-backed i18n mock (English) plus the extra context fields the
// switcher touches.
jest.mock('@/contexts/I18nContext', () => {
  const m = require('@/test-utils/i18nMock').i18nMock('en')
  return {
    ...m,
    useI18n: () => ({
      ...m.useI18n(),
      currentLanguage: 'en',
      changeLanguage: jest.fn(),
      changeLocale: jest.fn(),
    }),
  }
})
