import { fireEvent, render, screen } from '@testing-library/react'

import { DemoEnvBadge } from '../DemoEnvBadge'

const mockLocale = { locale: 'de' }
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ locale: mockLocale.locale, t: (k: string) => k }),
}))

const mockIsDemoHost = jest.fn()
jest.mock('@/lib/utils/subdomain', () => ({
  isDemoHost: () => mockIsDemoHost(),
}))

describe('DemoEnvBadge', () => {
  beforeEach(() => {
    mockIsDemoHost.mockReset()
    mockLocale.locale = 'de'
  })

  it('renders nothing outside the demo environment', () => {
    mockIsDemoHost.mockReturnValue(false)
    const { container } = render(<DemoEnvBadge />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the German badge on a demo host and toggles the details', () => {
    mockIsDemoHost.mockReturnValue(true)
    render(<DemoEnvBadge />)
    const button = screen.getByRole('button', { name: /Demo-Umgebung/ })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText(/jede Nacht um 4 Uhr/)).not.toBeInTheDocument()

    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/jede Nacht um 4 Uhr/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Schließen' }))
    expect(screen.queryByText(/jede Nacht um 4 Uhr/)).not.toBeInTheDocument()
  })

  it('uses English copy for the en locale', () => {
    mockIsDemoHost.mockReturnValue(true)
    mockLocale.locale = 'en'
    render(<DemoEnvBadge />)
    fireEvent.click(screen.getByRole('button', { name: /Demo environment/ }))
    expect(screen.getByText(/reset every night at 4 am/)).toBeInTheDocument()
  })
})
