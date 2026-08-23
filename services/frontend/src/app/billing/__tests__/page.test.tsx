/**
 * @jest-environment jsdom
 */
import { registerSlot } from '@/lib/extensions/slots'
import { render, screen } from '@testing-library/react'
import BillingPage from '../page'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string, d?: any) => (typeof d === 'string' ? d : k) }),
}))
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => <nav>{items.map((i: any) => i.label).join(' / ')}</nav>,
}))
jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

describe('/billing', () => {
  afterEach(() => registerSlot('StudentBilling', null as any))

  it('mounts the StudentBilling slot in expert variant', () => {
    const Stub = jest.fn(({ variant }: any) => <div data-testid="billing-stub">{variant}</div>)
    registerSlot('StudentBilling', Stub)
    render(<BillingPage />)
    expect(screen.getByTestId('billing-stub')).toHaveTextContent('expert')
    expect(screen.getByText(/Abo & Abrechnung/)).toBeInTheDocument()
  })

  it('community: shows the unavailable notice', () => {
    render(<BillingPage />)
    expect(screen.getByTestId('billing-unavailable')).toBeInTheDocument()
  })
})
