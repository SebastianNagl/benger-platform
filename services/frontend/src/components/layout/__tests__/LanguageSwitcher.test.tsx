/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LanguageSwitcher } from '../LanguageSwitcher'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

const mockUseI18n = require('@/contexts/I18nContext').useI18n

describe('LanguageSwitcher', () => {
  const changeLocale = jest.fn()

  function setup(locale: unknown) {
    mockUseI18n.mockReturnValue({
      locale,
      changeLocale,
      t: (key: string) =>
        key === 'layout.languageSwitcher.label' ? 'Choose language' : key,
    })
    return render(<LanguageSwitcher />)
  }

  beforeEach(() => jest.clearAllMocks())

  it.each([
    ['de', '🇩🇪', 'Deutsch'],
    ['en', '🇬🇧', 'English'],
    ['fr', '🇫🇷', 'Français'],
  ])('shows the %s flag on the trigger', (locale, flag, name) => {
    setup(locale)
    const trigger = screen.getByTestId('language-switcher')
    expect(trigger).toHaveTextContent(flag)
    expect(trigger).toHaveAttribute('data-locale', locale)
    expect(trigger).toHaveAttribute('aria-label', `Choose language: ${name}`)
    expect(trigger).toHaveAttribute('title', 'Choose language')
  })

  it('falls back to German for an unknown locale', () => {
    setup('xx')
    expect(screen.getByTestId('language-switcher')).toHaveTextContent('🇩🇪')
  })

  it('opens a menu listing every language under its own name', async () => {
    setup('de')
    await userEvent.click(screen.getByTestId('language-switcher'))

    const items = await screen.findAllByRole('menuitem')
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('Deutsch'),
      expect.stringContaining('English'),
      expect.stringContaining('Français'),
    ])
    expect(items[0]).toHaveAttribute('aria-current', 'true')
    expect(items[2]).toHaveAttribute('lang', 'fr')
    // Opening the menu alone changes nothing.
    expect(changeLocale).not.toHaveBeenCalled()
  })

  it('switches to the chosen language', async () => {
    setup('de')
    await userEvent.click(screen.getByTestId('language-switcher'))
    await userEvent.click(
      await screen.findByRole('menuitem', { name: /Français/ }),
    )
    expect(changeLocale).toHaveBeenCalledWith('fr')
  })

  it('is keyboard operable', async () => {
    setup('en')
    screen.getByTestId('language-switcher').focus()
    await userEvent.keyboard('{Enter}')
    expect(await screen.findByTestId('language-menu')).toBeInTheDocument()
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(changeLocale).toHaveBeenCalled()
  })

  it('keeps an overridden trigger class (student sidebar variant)', () => {
    mockUseI18n.mockReturnValue({
      locale: 'de',
      changeLocale,
      t: (k: string) => k,
    })
    render(<LanguageSwitcher className="custom-trigger" />)
    expect(screen.getByTestId('language-switcher')).toHaveClass(
      'custom-trigger',
    )
  })
})
