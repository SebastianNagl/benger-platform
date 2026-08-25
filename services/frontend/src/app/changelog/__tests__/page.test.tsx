/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'

import { PLATFORM_CHANGELOG } from '@/data/changelog'
import { registerChangelogEntries } from '@/lib/extensions/changelog'

import ChangelogPage from '../page'

let mockLocale: 'de' | 'en' = 'de'
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    locale: mockLocale,
  }),
}))

let mockUser: { is_superadmin?: boolean } | null = null
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser }),
}))

let mockUiMode: 'student' | 'expert' = 'expert'
jest.mock('@/hooks/useResolvedUiMode', () => ({
  useResolvedUiMode: () => mockUiMode,
}))

let mockStudentLockedHost = false
jest.mock('@/lib/utils/subdomain', () => ({
  isStudentLockedHost: () => mockStudentLockedHost,
}))

jest.mock('@/components/layout/LegalPageWrapper', () => ({
  LegalPageWrapper: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="legal-wrapper">{children}</div>
  ),
}))

// Mocked with a mutable array so each test controls the platform entries.
jest.mock('@/data/changelog', () => ({
  PLATFORM_CHANGELOG: [],
}))

describe('ChangelogPage', () => {
  beforeEach(() => {
    mockLocale = 'de'
    mockUiMode = 'expert'
    mockUser = null
    mockStudentLockedHost = false
    PLATFORM_CHANGELOG.length = 0
    PLATFORM_CHANGELOG.push(
      {
        date: '2026-08-24',
        audience: 'both',
        text: { de: 'Plattform beide', en: 'Platform both' },
      },
      {
        date: '2026-08-20',
        audience: 'benger',
        text: { de: 'Nur BenGER', en: 'BenGER only' },
      },
    )
    registerChangelogEntries('extended', [
      {
        date: '2026-08-24',
        audience: 'vertretbar',
        text: { de: 'Nur Vertretbar', en: 'Vertretbar only' },
      },
    ])
  })

  it('renders title and intro in the legal wrapper', () => {
    render(<ChangelogPage />)
    expect(screen.getByTestId('legal-wrapper')).toBeInTheDocument()
    expect(screen.getByText('changelog.title')).toBeInTheDocument()
    expect(screen.getByText('changelog.intro')).toBeInTheDocument()
  })

  it('shows benger and both entries, hides vertretbar entries, in expert mode', () => {
    render(<ChangelogPage />)
    expect(screen.getByText('Plattform beide')).toBeInTheDocument()
    expect(screen.getByText('Nur BenGER')).toBeInTheDocument()
    expect(screen.queryByText('Nur Vertretbar')).not.toBeInTheDocument()
  })

  it('shows vertretbar and both entries, hides benger entries, in student mode', () => {
    mockUiMode = 'student'
    render(<ChangelogPage />)
    expect(screen.getByText('Plattform beide')).toBeInTheDocument()
    expect(screen.getByText('Nur Vertretbar')).toBeInTheDocument()
    expect(screen.queryByText('Nur BenGER')).not.toBeInTheDocument()
  })

  it('falls back to vertretbar for anonymous visitors on a student-locked host (pre-registration window)', () => {
    // useResolvedUiMode still says 'expert' before StudentShell registers.
    mockUiMode = 'expert'
    mockStudentLockedHost = true
    render(<ChangelogPage />)
    expect(screen.getByText('Nur Vertretbar')).toBeInTheDocument()
    expect(screen.queryByText('Nur BenGER')).not.toBeInTheDocument()
  })

  it('excludes superadmins from the student-locked-host fallback (view switch stays authoritative)', () => {
    mockUiMode = 'expert'
    mockStudentLockedHost = true
    mockUser = { is_superadmin: true }
    render(<ChangelogPage />)
    expect(screen.getByText('Nur BenGER')).toBeInTheDocument()
    expect(screen.queryByText('Nur Vertretbar')).not.toBeInTheDocument()
  })

  it('keeps the superadmin view switch to student mode authoritative on any host', () => {
    mockUiMode = 'student'
    mockStudentLockedHost = false
    mockUser = { is_superadmin: true }
    render(<ChangelogPage />)
    expect(screen.getByText('Nur Vertretbar')).toBeInTheDocument()
    expect(screen.queryByText('Nur BenGER')).not.toBeInTheDocument()
  })

  it('groups entries under localized date headings, newest first', () => {
    render(<ChangelogPage />)
    const headings = screen.getAllByRole('heading', { level: 2 })
    expect(headings.map((h) => h.textContent)).toEqual([
      '24. August 2026',
      '20. August 2026',
    ])
  })

  it('renders entry text in the active locale', () => {
    mockLocale = 'en'
    render(<ChangelogPage />)
    expect(screen.getByText('Platform both')).toBeInTheDocument()
    expect(screen.queryByText('Plattform beide')).not.toBeInTheDocument()
    const headings = screen.getAllByRole('heading', { level: 2 })
    expect(headings[0].textContent).toBe('24 August 2026')
  })

  it('renders the empty state when no entries match', () => {
    PLATFORM_CHANGELOG.length = 0
    registerChangelogEntries('extended', [])
    render(<ChangelogPage />)
    expect(screen.getByText('changelog.empty')).toBeInTheDocument()
  })
})
