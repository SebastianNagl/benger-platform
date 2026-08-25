/**
 * @jest-environment jsdom
 */
import { registerSlot } from '@/lib/extensions/slots'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ParticipantCard } from '../ParticipantCard'

const mockConfirm = jest.fn()
const mockAddToast = jest.fn()
jest.mock('@/hooks/useDialogs', () => ({ useConfirm: () => mockConfirm }))
jest.mock('@/components/shared/Toast', () => ({ useToast: () => ({ addToast: mockAddToast }) }))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string, def?: any) => (typeof def === 'string' ? def : key) }),
}))
const mockGet = jest.fn()
const mockLeave = jest.fn()
jest.mock('@/lib/api/shares', () => ({
  sharesAPI: {
    getParticipation: (...a: any[]) => mockGet(...a),
    leaveProject: (...a: any[]) => mockLeave(...a),
  },
}))

beforeEach(() => {
  jest.clearAllMocks()
  registerSlot('ProjectCohortLeaderboard', null as any)
})

describe('ParticipantCard', () => {
  it('shows how the user joined, confirms, leaves and calls onLeft', async () => {
    mockGet.mockResolvedValue({ tier: 'participant', via: 'share', can_leave: true, cannot_leave_reason: null })
    mockConfirm.mockResolvedValue(true)
    mockLeave.mockResolvedValue(undefined)
    const onLeft = jest.fn()
    render(<ParticipantCard projectId="p1" via="share" onLeft={onLeft} />)
    expect(screen.getByTestId('participant-via')).toHaveTextContent('Beigetreten')
    fireEvent.click(await screen.findByTestId('participant-leave'))
    await waitFor(() => expect(mockLeave).toHaveBeenCalledWith('p1'))
    expect(onLeft).toHaveBeenCalled()
    expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'success')
  })

  it('cancelled confirm does nothing; leave error toasts', async () => {
    mockGet.mockResolvedValue({ tier: 'participant', via: 'share', can_leave: true, cannot_leave_reason: null })
    mockConfirm.mockResolvedValueOnce(false)
    const onLeft = jest.fn()
    render(<ParticipantCard projectId="p1" via="share" onLeft={onLeft} />)
    fireEvent.click(await screen.findByTestId('participant-leave'))
    await waitFor(() => expect(mockConfirm).toHaveBeenCalled())
    expect(mockLeave).not.toHaveBeenCalled()
    mockConfirm.mockResolvedValueOnce(true)
    mockLeave.mockRejectedValueOnce(new Error('boom'))
    fireEvent.click(screen.getByTestId('participant-leave'))
    await waitFor(() => expect(mockAddToast).toHaveBeenCalledWith('boom', 'error'))
    expect(onLeft).not.toHaveBeenCalled()
  })

  it('explains why leaving is impossible (purchase / org) and hosts the cohort slot', async () => {
    mockGet.mockResolvedValue({ tier: 'participant', via: 'entitlement', can_leave: false, cannot_leave_reason: 'entitlement_not_leavable' })
    const Cohort = ({ projectId }: any) => <div data-testid="cohort-stub">{projectId}</div>
    registerSlot('ProjectCohortLeaderboard', Cohort)
    const { unmount } = render(<ParticipantCard projectId="p1" via={null} onLeft={jest.fn()} />)
    expect(await screen.findByTestId('participant-cannot-leave')).toHaveTextContent('Gekaufter')
    expect(screen.queryByTestId('participant-leave')).not.toBeInTheDocument()
    expect(screen.getByTestId('cohort-stub')).toHaveTextContent('p1')
    unmount()

    mockGet.mockResolvedValue({ tier: 'participant', via: 'org_exam', can_leave: false, cannot_leave_reason: 'org_membership' })
    render(<ParticipantCard projectId="p2" via="org_exam" onLeft={jest.fn()} />)
    expect(await screen.findByTestId('participant-cannot-leave')).toHaveTextContent('Organisation')
  })

  it('falls back to the via prop when the participation fetch fails', async () => {
    mockGet.mockRejectedValue(new Error('403'))
    render(<ParticipantCard projectId="p1" via="org_exam" onLeft={jest.fn()} />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(screen.getByTestId('participant-via')).toBeInTheDocument()
    expect(screen.queryByTestId('participant-leave')).not.toBeInTheDocument()
    expect(screen.queryByTestId('participant-cannot-leave')).not.toBeInTheDocument()
  })
})
