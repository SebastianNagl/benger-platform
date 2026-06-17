/**
 * Tests for the Leaderboards page (community edition).
 *
 * In the community build the human / co-creation slots are unregistered, so
 * useSlot returns null: the page defaults to the LLM tab and only the LLMs
 * tab button renders. We mock the slot registry to exercise both the
 * community default and the extended-present branch.
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    // t(key, fallback?) — page passes `t(key) || fallback`, so returning the
    // fallback path is fine; here we return the key's last segment for brevity.
    t: (key: string) => {
      const map: Record<string, string> = {
        'navigation.dashboard': 'Dashboard',
        'navigation.leaderboards': 'Leaderboards',
        'leaderboards.title': 'Leaderboards',
        'leaderboards.humanAnnotators': 'Human Annotators',
        'leaderboards.coCreation': 'Co-Creation',
        'leaderboards.llms': 'LLMs',
        'leaderboards.refreshHint': 'Updated daily',
      }
      return map[key] || ''
    },
  }),
}))

jest.mock('@/components/auth/AuthGuard', () => ({
  AuthGuard: ({ children }: any) => <>{children}</>,
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <div data-testid="breadcrumb">
      {items.map((i: any, idx: number) => (
        <span key={idx}>{i.label}</span>
      ))}
    </div>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))

jest.mock('@/components/leaderboards/LLMLeaderboardTable', () => ({
  LLMLeaderboardTable: () => (
    <div data-testid="llm-leaderboard-table">LLM Leaderboard</div>
  ),
}))

// Slot registry — toggled per test via the mocked implementation.
const mockUseSlot = jest.fn()
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockUseSlot(name),
}))

import LeaderboardsPage from '../page'

beforeEach(() => {
  jest.clearAllMocks()
})

describe('LeaderboardsPage — community edition (no slots)', () => {
  beforeEach(() => {
    mockUseSlot.mockReturnValue(null)
  })

  it('renders the LLM leaderboard table by default', () => {
    render(<LeaderboardsPage />)
    expect(screen.getByTestId('llm-leaderboard-table')).toBeInTheDocument()
  })

  it('renders the page heading and refresh hint', () => {
    render(<LeaderboardsPage />)
    expect(
      screen.getByRole('heading', { name: 'Leaderboards' })
    ).toBeInTheDocument()
    expect(screen.getByText('Updated daily')).toBeInTheDocument()
  })

  it('shows the LLMs tab but not the human / co-creation tabs', () => {
    render(<LeaderboardsPage />)
    expect(screen.getByRole('button', { name: 'LLMs' })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Human Annotators' })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Co-Creation' })
    ).not.toBeInTheDocument()
  })

  it('renders the breadcrumb trail', () => {
    render(<LeaderboardsPage />)
    const crumb = screen.getByTestId('breadcrumb')
    expect(crumb).toHaveTextContent('Dashboard')
    expect(crumb).toHaveTextContent('Leaderboards')
  })
})

describe('LeaderboardsPage — extended edition (slots present)', () => {
  function HumanTab() {
    return <div data-testid="human-tab">Human Tab</div>
  }
  function CoCreationTab() {
    return <div data-testid="cocreation-tab">Co-Creation Tab</div>
  }

  beforeEach(() => {
    mockUseSlot.mockImplementation((name: string) => {
      if (name === 'AnnotatorLeaderboardTab') return HumanTab
      if (name === 'CoCreationLeaderboardTab') return CoCreationTab
      return null
    })
  })

  it('defaults to the human tab when the annotator slot is registered', () => {
    render(<LeaderboardsPage />)
    expect(screen.getByTestId('human-tab')).toBeInTheDocument()
    expect(
      screen.queryByTestId('llm-leaderboard-table')
    ).not.toBeInTheDocument()
  })

  it('renders all three tab buttons when both slots are present', () => {
    render(<LeaderboardsPage />)
    expect(
      screen.getByRole('button', { name: 'Human Annotators' })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Co-Creation' })
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'LLMs' })).toBeInTheDocument()
  })

  it('switches to the co-creation tab on click', async () => {
    const user = userEvent.setup()
    render(<LeaderboardsPage />)
    await user.click(screen.getByRole('button', { name: 'Co-Creation' }))
    expect(screen.getByTestId('cocreation-tab')).toBeInTheDocument()
  })

  it('switches to the LLM tab on click', async () => {
    const user = userEvent.setup()
    render(<LeaderboardsPage />)
    await user.click(screen.getByRole('button', { name: 'LLMs' }))
    expect(screen.getByTestId('llm-leaderboard-table')).toBeInTheDocument()
  })

  it('switches back to the human tab from another tab', async () => {
    const user = userEvent.setup()
    render(<LeaderboardsPage />)
    await user.click(screen.getByRole('button', { name: 'LLMs' }))
    await user.click(screen.getByRole('button', { name: 'Human Annotators' }))
    expect(screen.getByTestId('human-tab')).toBeInTheDocument()
  })
})
