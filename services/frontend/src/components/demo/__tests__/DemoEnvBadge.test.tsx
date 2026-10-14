import { fireEvent, render, screen } from '@testing-library/react'

import { DemoEnvBadge } from '../DemoEnvBadge'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ locale: 'de', t: (k: string) => k }),
}))

const mockIsDemoHost = jest.fn()
jest.mock('@/lib/utils/subdomain', () => ({
  isDemoHost: () => mockIsDemoHost(),
}))

describe('DemoEnvBadge', () => {
  beforeEach(() => {
    mockIsDemoHost.mockReset()
  })

  it('renders nothing outside the demo environment', () => {
    mockIsDemoHost.mockReturnValue(false)
    const { container } = render(<DemoEnvBadge />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the badge on a demo host and toggles the details', () => {
    mockIsDemoHost.mockReturnValue(true)
    render(<DemoEnvBadge />)
    const button = screen.getByRole('button', { name: /demo\.envBadge\.label/ })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(button).toHaveAttribute('title', 'demo.envBadge.body')
    expect(screen.queryByText('demo.envBadge.body')).not.toBeInTheDocument()

    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('demo.envBadge.body')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'common.close' }))
    expect(screen.queryByText('demo.envBadge.body')).not.toBeInTheDocument()
  })
})
