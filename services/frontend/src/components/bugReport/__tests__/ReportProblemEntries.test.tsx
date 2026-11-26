/**
 * @jest-environment jsdom
 *
 * The entry points of "Report a problem" and the host: nothing renders and
 * nothing records while the `bug_reports` flag is off; with it on the menu
 * row, the footer link and the error page button open the shared dialog
 * with their source, and superadmins get the link to the report list.
 */
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen } from '@testing-library/react'

import { resetBugReportRecorderForTests } from '@/lib/bugReport/recorder'
import {
  resetBugReportDialogForTests,
  useBugReportDialog,
} from '@/lib/bugReport/store'

import { BugReportHost } from '../BugReportHost'
import {
  ReportProblemButton,
  ReportProblemFooterLink,
  ReportProblemMenuEntry,
} from '../ReportProblemEntries'

let mockFlagOn = false
let mockUser: any = { id: 'u1', is_superadmin: false }
jest.mock('@/lib/featureFlags', () => ({
  useFeatureFlag: () => mockFlagOn,
  useFeatureFlagStatus: () => (mockFlagOn ? 'on' : 'off'),
  getFeatureFlagMap: () => ({ bug_reports: mockFlagOn }),
}))
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser }),
  useOptionalAuth: () => ({ user: mockUser, organizations: [] }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'de' }),
}))
jest.mock('@/hooks/useResolvedUiMode', () => ({
  useResolvedUiMode: () => 'expert',
}))
jest.mock('next/navigation', () => ({
  usePathname: () => '/projects/p-1',
  useParams: () => ({ id: 'p-1' }),
}))
jest.mock('next/link', () => {
  const Link = ({ children, href, ...rest }: any) => (
    <a href={href} {...rest}>
      {children}
    </a>
  )
  return { __esModule: true, default: Link }
})

function DialogState() {
  const { open, source } = useBugReportDialog()
  return <output data-testid="state">{`${open}:${source}`}</output>
}

beforeEach(() => {
  mockFlagOn = false
  mockUser = { id: 'u1', is_superadmin: false }
  resetBugReportDialogForTests()
  resetBugReportRecorderForTests()
})

describe('report a problem entries', () => {
  it('render nothing while the flag is off', () => {
    const originalFetch = window.fetch
    const { container } = render(
      <>
        <ReportProblemMenuEntry />
        <ReportProblemFooterLink />
        <ReportProblemButton />
        <BugReportHost />
      </>,
    )
    expect(container).toBeEmptyDOMElement()
    expect(window.fetch).toBe(originalFetch)
  })

  it('open the shared dialog with their source', () => {
    mockFlagOn = true
    const onNavigate = jest.fn()
    render(
      <>
        <ReportProblemMenuEntry onNavigate={onNavigate} />
        <ReportProblemFooterLink />
        <ReportProblemButton source="error-page" />
        <DialogState />
      </>,
    )
    expect(screen.queryByTestId('auth-menu-bug-reports')).toBeNull()
    fireEvent.click(screen.getByTestId('auth-menu-report-problem'))
    expect(onNavigate).toHaveBeenCalled()
    expect(screen.getByTestId('state')).toHaveTextContent('true:menu')
    fireEvent.click(screen.getByTestId('footer-report-problem'))
    expect(screen.getByTestId('state')).toHaveTextContent('true:footer')
    fireEvent.click(screen.getByTestId('error-report-problem'))
    expect(screen.getByTestId('state')).toHaveTextContent('true:error-page')
  })

  it('link superadmins to the report list', () => {
    mockFlagOn = true
    mockUser = { id: 'admin', is_superadmin: true }
    render(<ReportProblemMenuEntry />)
    expect(screen.getByTestId('auth-menu-bug-reports')).toHaveAttribute(
      'href',
      '/admin/bug-reports',
    )
  })

  it('the host records while on and shows the dialog when opened', async () => {
    mockFlagOn = true
    const originalFetch = window.fetch
    render(
      <>
        <BugReportHost />
        <ReportProblemFooterLink />
      </>,
    )
    expect(window.fetch).not.toBe(originalFetch)
    await act(async () => {
      fireEvent.click(screen.getByTestId('footer-report-problem'))
    })
    const preview = JSON.parse(
      (await screen.findByTestId('bug-report-context')).textContent!,
    )
    expect(preview).toMatchObject({
      source: 'footer',
      route_params: { id: 'p-1' },
      ui_mode: 'expert',
      navigation: [expect.objectContaining({ path: '/projects/p-1' })],
    })
  })
})
