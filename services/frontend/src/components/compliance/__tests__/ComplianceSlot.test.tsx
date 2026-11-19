/**
 * Compliance slots render only while the compliance overlay's master flag
 * (`extension.compliance`) is on for the viewer: the /compliance route
 * shells (ComplianceDashboard, AssessmentDetail) and the inline findings
 * slot on the analysis run page. The slot and active-overlay registries are
 * the real ones; only the "active overlays known yet" signal is controlled.
 */

import '@testing-library/jest-dom'
import { act, render, screen } from '@testing-library/react'

import ComplianceAssessmentPage from '@/app/compliance/assessments/[assessmentId]/page'
import CompliancePage from '@/app/compliance/page'
import {
  COMPLIANCE_SLOTS,
  ComplianceInlineSlot,
  ComplianceRouteShell,
} from '@/components/compliance/ComplianceSlot'
import {
  _resetActiveExtensionsForTests,
  setActiveExtensions,
} from '@/lib/extensions/active'
import { setRegistrationOwner } from '@/lib/extensions/owner'
import { registerSlot } from '@/lib/extensions/slots'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

let mockReady = true
jest.mock('@/lib/featureFlags', () => ({
  ...jest.requireActual('@/lib/featureFlags'),
  useActiveExtensionsReady: () => mockReady,
}))

let mockEnabled = false
let mockLoaded = false
jest.mock('@/lib/extensions/enabled', () => ({
  ...jest.requireActual('@/lib/extensions/enabled'),
  isExtensionEnabled: (name: string) => mockEnabled && name === 'compliance',
}))
jest.mock('@/lib/extensions', () => ({
  ...jest.requireActual('@/lib/extensions'),
  isExtensionLoaded: (name: string) => mockLoaded && name === 'compliance',
}))

jest.mock('next/navigation', () => ({
  useParams: () => ({ assessmentId: 'assessment-7' }),
}))

function Dashboard() {
  return <div data-testid="overlay-dashboard">dashboard</div>
}
function Detail({ assessmentId }: { assessmentId: string }) {
  return <div data-testid="overlay-detail">assessment {assessmentId}</div>
}
function Findings({ run }: { run: { id: string } }) {
  return <div data-testid="overlay-findings">findings of {run.id}</div>
}

/** Register as the compliance overlay's loader would. */
function registerAsCompliance() {
  setRegistrationOwner('compliance')
  try {
    registerSlot(COMPLIANCE_SLOTS.dashboard, Dashboard)
    registerSlot(COMPLIANCE_SLOTS.assessmentDetail, Detail)
    registerSlot(COMPLIANCE_SLOTS.analysisRunFindings, Findings)
  } finally {
    setRegistrationOwner(null)
  }
}

beforeAll(() => {
  registerAsCompliance()
})

beforeEach(() => {
  mockReady = true
  mockEnabled = false
  mockLoaded = false
  _resetActiveExtensionsForTests()
})

describe('compliance route shells', () => {
  it('render the overlay pages only while the compliance flag is on', () => {
    const { unmount } = render(<CompliancePage />)
    expect(screen.getByTestId('compliance-unavailable')).toBeInTheDocument()
    expect(screen.queryByTestId('overlay-dashboard')).toBeNull()
    expect(screen.getByText('Compliance is not available')).toBeInTheDocument()

    act(() => setActiveExtensions(['compliance']))
    expect(screen.getByTestId('overlay-dashboard')).toBeInTheDocument()
    expect(screen.queryByTestId('compliance-unavailable')).toBeNull()

    // switched off at runtime: the page falls back at once
    act(() => setActiveExtensions([]))
    expect(screen.queryByTestId('overlay-dashboard')).toBeNull()
    expect(screen.getByTestId('compliance-unavailable')).toBeInTheDocument()
    unmount()
  })

  it('pass the assessment id to AssessmentDetail', () => {
    setActiveExtensions(['compliance'])
    render(<ComplianceAssessmentPage />)
    expect(screen.getByTestId('overlay-detail')).toHaveTextContent(
      'assessment assessment-7',
    )
  })

  it('wait instead of flashing the notice while the overlays are unknown', () => {
    mockReady = false
    render(<CompliancePage />)
    expect(screen.getByTestId('compliance-loading')).toBeInTheDocument()
    expect(screen.queryByTestId('compliance-unavailable')).toBeNull()
  })

  it('show the notice when the active overlay registers no such page', () => {
    mockEnabled = true
    mockLoaded = true
    setActiveExtensions(['compliance'])
    render(
      // a slot name the overlay did not register
      <ComplianceRouteShell slot={'NotRegistered' as never} />,
    )
    expect(screen.getByTestId('compliance-unavailable')).toBeInTheDocument()
  })

  it('stay loading for a not yet registered slot of an included overlay', () => {
    mockEnabled = true
    mockLoaded = false
    setActiveExtensions(['compliance'])
    render(<ComplianceRouteShell slot={'NotRegistered' as never} />)
    expect(screen.getByTestId('compliance-loading')).toBeInTheDocument()
  })
})

describe('inline compliance slot', () => {
  const run = { id: 'run-1' }

  it('renders the findings only while the compliance flag is on', () => {
    const { container } = render(
      <div data-testid="host">
        <ComplianceInlineSlot
          slot="AnalysisRunFindings"
          props={{ run, estimates: [], projectId: 'p' }}
        />
      </div>,
    )
    expect(screen.queryByTestId('overlay-findings')).toBeNull()
    // nothing at all, no placeholder
    expect(screen.getByTestId('host')).toBeEmptyDOMElement()

    act(() => setActiveExtensions(['compliance']))
    expect(screen.getByTestId('overlay-findings')).toHaveTextContent(
      'findings of run-1',
    )

    act(() => setActiveExtensions(['extended']))
    expect(screen.queryByTestId('overlay-findings')).toBeNull()
    expect(
      container.querySelector('[data-testid="host"]'),
    ).toBeEmptyDOMElement()
  })

  it('ignores a component another owner registered while compliance is off', () => {
    setRegistrationOwner('extended')
    const Other = () => <div data-testid="other-owner">other</div>
    try {
      registerSlot('AnalysisRunFindings', Other)
    } finally {
      setRegistrationOwner(null)
    }
    jest.spyOn(console, 'warn').mockImplementation(() => undefined)
    act(() => setActiveExtensions(['extended']))
    render(
      <ComplianceInlineSlot
        slot="AnalysisRunFindings"
        props={{ run, estimates: [], projectId: 'p' }}
      />,
    )
    expect(screen.queryByTestId('other-owner')).toBeNull()
    expect(screen.queryByTestId('overlay-findings')).toBeNull()
  })
})
