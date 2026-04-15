import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LanguageSwitcher } from '../LanguageSwitcher'

// Mock the I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

const mockUseI18n = require('@/contexts/I18nContext').useI18n

describe('LanguageSwitcher', () => {
  const mockChangeLocale = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('mounting behavior', () => {
    it('renders correctly and handles mounting behavior', () => {
      mockUseI18n.mockReturnValue({
        locale: 'en',
        changeLocale: mockChangeLocale,
      })

      const { container } = render(<LanguageSwitcher />)

      // After mounting, should render interactive button (this tests the actual behavior)
      const button = container.querySelector(
        'button[data-testid="language-switcher"]'
      )
      expect(button).toBeInTheDocument()

      // Should have correct flag for English locale
      expect(button).toHaveTextContent('🇺🇸')

      // Should have correct container structure
      const flexContainer = container.querySelector('.flex.size-6')
      expect(flexContainer).toBeInTheDocument()
    })

    it('shows interactive button after mounting', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toBeInTheDocument()
      expect(button).toHaveAttribute('data-testid', 'language-switcher')
    })
  })

  describe('language switching', () => {
    it('shows German flag for German locale', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toHaveTextContent('🇩🇪')
      expect(button).toHaveAttribute(
        'aria-label',
        'Language: Deutsch → English'
      )
    })

    it('shows US flag for English locale', () => {
      mockUseI18n.mockReturnValue({
        locale: 'en',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toHaveTextContent('🇺🇸')
      expect(button).toHaveAttribute(
        'aria-label',
        'Language: English → Deutsch'
      )
    })

    it('calls changeLocale with correct target language from German', async () => {
      const user = userEvent.setup()
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      await user.click(button)

      expect(mockChangeLocale).toHaveBeenCalledWith('en')
      expect(mockChangeLocale).toHaveBeenCalledTimes(1)
    })

    it('calls changeLocale with correct target language from English', async () => {
      const user = userEvent.setup()
      mockUseI18n.mockReturnValue({
        locale: 'en',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      await user.click(button)

      expect(mockChangeLocale).toHaveBeenCalledWith('de')
      expect(mockChangeLocale).toHaveBeenCalledTimes(1)
    })

    it('handles changeLocale errors gracefully', async () => {
      const user = userEvent.setup()
      const mockChangeLocaleError = jest.fn().mockImplementation(() => {
        throw new Error('Language change error')
      })

      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocaleError,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')

      // Should not throw error
      expect(() => user.click(button)).not.toThrow()
      await user.click(button)
      expect(mockChangeLocaleError).toHaveBeenCalledWith('en')
    })
  })

  describe('styling and appearance', () => {
    it('applies correct button styling', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

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

    it('includes touch target for mobile devices', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      const { container } = render(<LanguageSwitcher />)

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

    it('applies correct flag styling', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const flag = screen.getByRole('img')
      expect(flag).toHaveClass('text-sm')
      expect(flag).toHaveAttribute('role', 'img')
    })
  })

  describe('accessibility', () => {
    it('provides proper aria-label for German locale', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute(
        'aria-label',
        'Language: Deutsch → English'
      )
    })

    it('provides proper aria-label for English locale', () => {
      mockUseI18n.mockReturnValue({
        locale: 'en',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute(
        'aria-label',
        'Language: English → Deutsch'
      )
    })

    it('provides title attribute for tooltip', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('title', 'Language: Deutsch → English')
    })

    it('marks flag with proper aria-label', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const flag = screen.getByRole('img')
      expect(flag).toHaveAttribute('aria-label', 'Deutsch')
    })

    it('has proper button type', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute('type', 'button')
    })

    it('provides test id for automated testing', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByTestId('language-switcher')
      expect(button).toBeInTheDocument()
    })
  })

  describe('edge cases', () => {
    it('handles undefined locale gracefully', () => {
      mockUseI18n.mockReturnValue({
        locale: undefined,
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toHaveTextContent('🇩🇪') // Falls back to German
      expect(button).toHaveAttribute(
        'aria-label',
        'Language: Deutsch → English'
      )
    })

    it('handles null locale gracefully', () => {
      mockUseI18n.mockReturnValue({
        locale: null,
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toHaveTextContent('🇩🇪') // Falls back to German
    })

    it('handles invalid locale gracefully', () => {
      mockUseI18n.mockReturnValue({
        locale: 'fr', // Invalid locale
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button).toHaveTextContent('🇩🇪') // Falls back to German
    })
  })

  describe('locale constants', () => {
    it('uses correct flag emojis for each locale', () => {
      // Test German locale
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      const { rerender } = render(<LanguageSwitcher />)
      expect(screen.getByRole('button')).toHaveTextContent('🇩🇪')

      // Test English locale
      mockUseI18n.mockReturnValue({
        locale: 'en',
        changeLocale: mockChangeLocale,
      })

      rerender(<LanguageSwitcher />)
      expect(screen.getByRole('button')).toHaveTextContent('🇺🇸')
    })

    it('uses correct locale names for accessibility', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const flag = screen.getByRole('img')
      expect(flag).toHaveAttribute('aria-label', 'Deutsch')

      const button = screen.getByRole('button')
      expect(button).toHaveAttribute(
        'aria-label',
        'Language: Deutsch → English'
      )
    })
  })

  describe('keyboard interaction', () => {
    it('supports keyboard activation', async () => {
      const user = userEvent.setup()
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')

      // Focus and activate with Enter
      button.focus()
      await user.keyboard('{Enter}')

      expect(mockChangeLocale).toHaveBeenCalledWith('en')
    })

    it('supports space key activation', async () => {
      const user = userEvent.setup()
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')

      // Focus and activate with Space
      button.focus()
      await user.keyboard(' ')

      expect(mockChangeLocale).toHaveBeenCalledWith('en')
    })
  })

  describe('state management', () => {
    it('properly toggles between locales', async () => {
      const user = userEvent.setup()

      // Start with German
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      const { rerender } = render(<LanguageSwitcher />)

      let button = screen.getByRole('button')
      expect(button).toHaveTextContent('🇩🇪')
      await user.click(button)
      expect(mockChangeLocale).toHaveBeenCalledWith('en')

      // Simulate locale change to English
      mockUseI18n.mockReturnValue({
        locale: 'en',
        changeLocale: mockChangeLocale,
      })

      rerender(<LanguageSwitcher />)

      button = screen.getByRole('button')
      expect(button).toHaveTextContent('🇺🇸')
      await user.click(button)
      expect(mockChangeLocale).toHaveBeenCalledWith('de')
    })

    it('updates aria labels when locale changes', () => {
      mockUseI18n.mockReturnValue({
        locale: 'de',
        changeLocale: mockChangeLocale,
      })

      const { rerender } = render(<LanguageSwitcher />)

      let button = screen.getByRole('button')
      expect(button).toHaveAttribute(
        'aria-label',
        'Language: Deutsch → English'
      )

      // Change to English
      mockUseI18n.mockReturnValue({
        locale: 'en',
        changeLocale: mockChangeLocale,
      })

      rerender(<LanguageSwitcher />)

      button = screen.getByRole('button')
      expect(button).toHaveAttribute(
        'aria-label',
        'Language: English → Deutsch'
      )
    })
  })
})
