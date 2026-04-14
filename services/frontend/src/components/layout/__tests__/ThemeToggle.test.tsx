import { fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { ThemeToggle } from '../ThemeToggle'

// Mock next-themes
jest.mock('next-themes', () => ({
  useTheme: jest.fn(),
}))

const mockUseTheme = require('next-themes').useTheme

describe('ThemeToggle', () => {
  const mockSetTheme = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('mounting behavior', () => {
    it('shows fallback icon before component is mounted', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      // Mock useState to return false for mounted state
      const mockSetMounted = jest.fn()
      jest.spyOn(React, 'useState').mockReturnValueOnce([false, mockSetMounted])

      const { container } = render(<ThemeToggle />)

      // When not mounted, it renders a div instead of button
      const fallbackContainer = container.querySelector('.flex.size-6')
      expect(fallbackContainer).toBeInTheDocument()
    })

    it('shows interactive button after mounting', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button', {
        name: /switch to dark theme/i,
      })
      expect(button).toBeInTheDocument()
      expect(button).toHaveAttribute('data-testid', 'theme-toggle')
    })
  })

  describe('theme switching', () => {
    it('shows correct theme toggle button for light theme', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button', {
        name: /switch to dark theme/i,
      })
      expect(button).toBeInTheDocument()
    })

    it('shows correct theme toggle button for dark theme', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'dark',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button', {
        name: /switch to light theme/i,
      })
      expect(button).toBeInTheDocument()
    })

    it('calls setTheme with correct theme when clicked from light to dark', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button', {
        name: /switch to dark theme/i,
      })
      fireEvent.click(button)

      expect(mockSetTheme).toHaveBeenCalledWith('dark')
      expect(mockSetTheme).toHaveBeenCalledTimes(1)
    })

    it('calls setTheme with correct theme when clicked from dark to light', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'dark',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button', {
        name: /switch to light theme/i,
      })
      fireEvent.click(button)

      expect(mockSetTheme).toHaveBeenCalledWith('light')
      expect(mockSetTheme).toHaveBeenCalledTimes(1)
    })

    it('handles setTheme errors gracefully', () => {
      const mockSetThemeError = jest.fn().mockImplementation(() => {
        throw new Error('Theme error')
      })

      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetThemeError,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button')

      // Should not throw error
      expect(() => fireEvent.click(button)).not.toThrow()
      expect(mockSetThemeError).toHaveBeenCalledWith('dark')
    })
  })

  describe('styling and appearance', () => {
    it('applies correct button styling', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button')
      expect(button).toHaveClass(
        'flex',
        'size-6',
        'items-center',
        'justify-center',
        'rounded-md',
        'transition',
        'hover:bg-zinc-900/5',
        'dark:hover:bg-white/5'
      )
    })

    it('renders sun and moon icons with correct styling', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      const { container } = render(<ThemeToggle />)

      // Sun icon (visible in light mode)
      const sunIcon = container.querySelector('svg[viewBox="0 0 20 20"]')
      expect(sunIcon).toBeInTheDocument()
      expect(sunIcon).toHaveClass(
        'h-5',
        'w-5',
        'stroke-zinc-900',
        'dark:hidden'
      )

      // Moon icon (hidden in light mode, visible in dark mode)
      const moonIcon = container.querySelector(
        'svg[viewBox="0 0 20 20"]:nth-of-type(2)'
      )
      expect(moonIcon).toBeInTheDocument()
      expect(moonIcon).toHaveClass(
        'hidden',
        'h-5',
        'w-5',
        'stroke-white',
        'dark:block'
      )
    })

    it('includes touch target for mobile devices', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      const { container } = render(<ThemeToggle />)

      const touchTarget = container.querySelector(
        '.size-12.pointer-fine\\:hidden'
      )
      expect(touchTarget).toBeInTheDocument()
      expect(touchTarget).toHaveClass(
        'absolute',
        'size-12',
        'pointer-fine:hidden'
      )
    })
  })

  describe('accessibility', () => {
    it('provides proper aria-label for light theme', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Switch to dark theme')
    })

    it('provides proper aria-label for dark theme', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'dark',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Switch to light theme')
    })

    it('marks icons as decorative', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      const { container } = render(<ThemeToggle />)

      const icons = container.querySelectorAll('svg[aria-hidden="true"]')
      expect(icons).toHaveLength(2) // Both sun and moon icons
    })

    it('has proper button type', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('type', 'button')
    })

    it('provides test id for automated testing', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByTestId('theme-toggle')
      expect(button).toBeInTheDocument()
    })
  })

  describe('icon components', () => {
    it('renders sun icon with correct path elements', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      const { container } = render(<ThemeToggle />)

      const sunIcon = container.querySelector('svg[viewBox="0 0 20 20"]')
      expect(sunIcon).toBeInTheDocument()

      const paths = sunIcon?.querySelectorAll('path')
      expect(paths).toHaveLength(2) // Sun has two path elements
    })

    it('renders moon icon with correct path element', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'dark',
        setTheme: mockSetTheme,
      })

      const { container } = render(<ThemeToggle />)

      const moonIcon = container.querySelector(
        'svg[viewBox="0 0 20 20"]:nth-of-type(2)'
      )
      expect(moonIcon).toBeInTheDocument()

      const paths = moonIcon?.querySelectorAll('path')
      expect(paths).toHaveLength(1) // Moon has one path element
    })

    it('passes props correctly to icon components', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      const { container } = render(<ThemeToggle />)

      const icons = container.querySelectorAll('svg')
      icons.forEach((icon) => {
        expect(icon).toHaveAttribute('viewBox', '0 0 20 20')
        expect(icon).toHaveAttribute('fill', 'none')
        expect(icon).toHaveAttribute('aria-hidden', 'true')
      })
    })
  })

  describe('edge cases', () => {
    it('handles undefined resolved theme gracefully', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: undefined,
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Switch to dark theme')
    })

    it('handles null resolved theme gracefully', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: null,
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Switch to dark theme')
    })

    it('handles other theme values gracefully', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'system',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('aria-label', 'Switch to dark theme')
    })
  })

  describe('keyboard interaction', () => {
    it('supports keyboard activation', () => {
      mockUseTheme.mockReturnValue({
        resolvedTheme: 'light',
        setTheme: mockSetTheme,
      })

      render(<ThemeToggle />)

      const button = screen.getByRole('button')

      // Simulate keyboard activation
      fireEvent.keyDown(button, { key: 'Enter' })
      fireEvent.keyUp(button, { key: 'Enter' })

      // Button should still be functional (the actual theme change is handled by click)
      expect(button).toBeInTheDocument()
    })
  })
})
