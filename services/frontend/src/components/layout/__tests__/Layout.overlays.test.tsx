/**
 * @jest-environment jsdom
 *
 * The app shell renders its pages only once the enabled overlays have
 * registered their slots, so a page never shows its platform part first and
 * the overlay part (quick actions, cards, whole pages) a moment later. Its
 * waiting screen is the auth check's screen, so the spinner stays put.
 */
import { render, screen } from '@testing-library/react'

import { Layout } from '../Layout'

jest.mock('framer-motion', () => ({
  motion: {
    div: ({ children, className }: any) => (
      <div className={className}>{children}</div>
    ),
    aside: ({ children, className }: any) => (
      <aside className={className}>{children}</aside>
    ),
  },
}))
jest.mock('next/navigation', () => ({
  usePathname: () => '/projects/p1',
  useRouter: () => ({ replace: jest.fn() }),
}))
jest.mock('@/hooks/useHydration', () => ({ useHydration: () => true }))
jest.mock('@/stores', () => ({
  useUIStore: () => ({ isSidebarHidden: false }),
}))
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ isLoading: false }),
}))
const mockMode = { current: 'expert' as 'student' | 'expert' }
jest.mock('@/hooks/useResolvedUiMode', () => ({
  isExtendedEdition: () => true,
  useResolvedUiMode: () => mockMode.current,
}))
const mockReady = { flags: true, overlays: true }
jest.mock('@/lib/featureFlags', () => ({
  useActiveExtensionsReady: () => mockReady.flags,
}))
jest.mock('@/lib/extensions', () => ({
  useExtensionsSettled: () => mockReady.overlays,
}))
const mockSlots: Record<string, any> = {}
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockSlots[name] ?? null,
}))
jest.mock('../Header', () => ({ Header: () => <header /> }))
jest.mock('../Footer', () => ({ Footer: () => <footer /> }))
jest.mock('../Navigation', () => ({ Navigation: () => <nav /> }))
jest.mock('../SectionProvider', () => ({
  SectionProvider: ({ children }: any) => <>{children}</>,
}))

describe('Layout waits for the overlays', () => {
  beforeEach(() => {
    mockReady.flags = true
    mockReady.overlays = true
    mockMode.current = 'expert'
  })

  it('shows the loading screen, not the page, while overlays load', () => {
    mockReady.overlays = false
    render(<Layout allSections={{}}>page content</Layout>)
    expect(screen.getByTestId('ui-shell-skeleton')).toBeInTheDocument()
    expect(screen.queryByText('page content')).not.toBeInTheDocument()
  })

  it('shows the same loading screen while the extension switch is unknown', () => {
    mockReady.flags = false
    render(<Layout allSections={{}}>page content</Layout>)
    expect(screen.getByTestId('ui-shell-skeleton')).toHaveClass('fixed')
    expect(screen.queryByText('page content')).not.toBeInTheDocument()
  })

  it('renders the page once the overlays settled', () => {
    render(<Layout allSections={{}}>page content</Layout>)
    expect(screen.queryByTestId('ui-shell-skeleton')).not.toBeInTheDocument()
    expect(screen.getByText('page content')).toBeInTheDocument()
  })
})
