/**
 * @jest-environment jsdom
 *
 * The GlobalOnboarding slot (extended setup modal + role tour) mounts in both
 * shells, tells the slot which shell it is in, and is absent when nothing is
 * registered (community edition).
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
  usePathname: () => '/student',
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

function Onboarding({ shell }: { shell: string }) {
  return <div data-testid="onboarding" data-shell={shell} />
}

function StudentShell({ children }: { children: React.ReactNode }) {
  return <div data-testid="student-shell">{children}</div>
}

describe('Layout GlobalOnboarding slot', () => {
  beforeEach(() => {
    for (const key of Object.keys(mockSlots)) delete mockSlots[key]
  })

  it('mounts in the expert shell', () => {
    mockMode.current = 'expert'
    mockSlots.GlobalOnboarding = Onboarding
    render(<Layout allSections={{}}>content</Layout>)
    expect(screen.getByTestId('onboarding')).toHaveAttribute(
      'data-shell',
      'expert',
    )
  })

  it('mounts in the student shell', () => {
    mockMode.current = 'student'
    mockSlots.GlobalOnboarding = Onboarding
    mockSlots.StudentShell = StudentShell
    render(<Layout allSections={{}}>content</Layout>)
    expect(screen.getByTestId('student-shell')).toBeInTheDocument()
    expect(screen.getByTestId('onboarding')).toHaveAttribute(
      'data-shell',
      'student',
    )
  })

  it('renders nothing when no extension registered the slot', () => {
    mockMode.current = 'expert'
    render(<Layout allSections={{}}>content</Layout>)
    expect(screen.queryByTestId('onboarding')).not.toBeInTheDocument()
  })
})
