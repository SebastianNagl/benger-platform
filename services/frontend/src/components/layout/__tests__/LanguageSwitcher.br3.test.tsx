/**
 * @jest-environment jsdom
 *
 * Branch coverage: LanguageSwitcher.tsx
 * Target: br0[0] L22-28 - !mounted pre-hydration path
 */

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => false,
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ locale: 'de', changeLocale: jest.fn() }),
}))

import { render } from '@testing-library/react'
import { LanguageSwitcher } from '../LanguageSwitcher'

describe('LanguageSwitcher br3', () => {
  it('renders pre-hydration state', () => {
    const { container } = render(<LanguageSwitcher />)
    expect(container.querySelector('button')).not.toBeInTheDocument()
    expect(container.textContent).toContain('\u{1F1E9}\u{1F1EA}') // German flag
  })
})
