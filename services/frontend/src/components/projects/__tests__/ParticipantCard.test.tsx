/**
 * @jest-environment jsdom
 */
import { registerSlot } from '@/lib/extensions/slots'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useEffect, useState } from 'react'
import { ParticipantCard } from '../ParticipantCard'

const mockConfirm = jest.fn()
const mockAddToast = jest.fn()
jest.mock('@/hooks/useDialogs', () => ({ useConfirm: () => mockConfirm }))
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, def?: any) => (typeof def === 'string' ? def : key),
  }),
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
    mockGet.mockResolvedValue({
      tier: 'participant',
      via: 'share',
      can_leave: true,
      cannot_leave_reason: null,
    })
    mockConfirm.mockResolvedValue(true)
    mockLeave.mockResolvedValue(undefined)
    const onLeft = jest.fn()
    render(<ParticipantCard projectId="p1" via="share" onLeft={onLeft} />)
    expect(screen.getByTestId('participant-via')).toHaveTextContent(
      'Beigetreten',
    )
    fireEvent.click(await screen.findByTestId('participant-leave'))
    await waitFor(() => expect(mockLeave).toHaveBeenCalledWith('p1'))
    expect(onLeft).toHaveBeenCalled()
    expect(mockAddToast).toHaveBeenCalledWith(expect.any(String), 'success')
  })

  it('cancelled confirm does nothing; leave error toasts', async () => {
    mockGet.mockResolvedValue({
      tier: 'participant',
      via: 'share',
      can_leave: true,
      cannot_leave_reason: null,
    })
    mockConfirm.mockResolvedValueOnce(false)
    const onLeft = jest.fn()
    render(<ParticipantCard projectId="p1" via="share" onLeft={onLeft} />)
    fireEvent.click(await screen.findByTestId('participant-leave'))
    await waitFor(() => expect(mockConfirm).toHaveBeenCalled())
    expect(mockLeave).not.toHaveBeenCalled()
    mockConfirm.mockResolvedValueOnce(true)
    mockLeave.mockRejectedValueOnce(new Error('boom'))
    fireEvent.click(screen.getByTestId('participant-leave'))
    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith('boom', 'error'),
    )
    expect(onLeft).not.toHaveBeenCalled()
  })

  it('explains why leaving is impossible (purchase / org) and hosts the cohort slot', async () => {
    mockGet.mockResolvedValue({
      tier: 'participant',
      via: 'entitlement',
      can_leave: false,
      cannot_leave_reason: 'entitlement_not_leavable',
    })
    const Cohort = ({ projectId }: any) => (
      <div data-testid="cohort-stub">{projectId}</div>
    )
    registerSlot('ProjectCohortLeaderboard', Cohort)
    const { unmount } = render(
      <ParticipantCard projectId="p1" via={null} onLeft={jest.fn()} />,
    )
    expect(
      await screen.findByTestId('participant-cannot-leave'),
    ).toHaveTextContent('Gekaufter')
    expect(screen.queryByTestId('participant-leave')).not.toBeInTheDocument()
    expect(screen.getByTestId('cohort-stub')).toHaveTextContent('p1')
    unmount()

    mockGet.mockResolvedValue({
      tier: 'participant',
      via: 'org_exam',
      can_leave: false,
      cannot_leave_reason: 'org_membership',
    })
    render(<ParticipantCard projectId="p2" via="org_exam" onLeft={jest.fn()} />)
    expect(
      await screen.findByTestId('participant-cannot-leave'),
    ).toHaveTextContent('Organisation')
  })

  it('org_exam with an empty cohort renders nothing', async () => {
    mockGet.mockResolvedValue({
      tier: 'participant',
      via: 'org_exam',
      can_leave: false,
      cannot_leave_reason: 'org_membership',
    })
    // Community edition: no cohort slot at all.
    const { unmount } = render(
      <ParticipantCard projectId="p1" via="org_exam" onLeft={jest.fn()} />,
    )
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    await waitFor(() =>
      expect(screen.queryByTestId('participant-card')).not.toBeInTheDocument(),
    )
    unmount()

    // Extended edition: the slot reports an empty cohort.
    const EmptyCohort = ({ onEmpty }: any) => {
      useEffect(() => onEmpty(true), [onEmpty])
      return <div data-testid="cohort-stub">empty</div>
    }
    registerSlot('ProjectCohortLeaderboard', EmptyCohort)
    render(<ParticipantCard projectId="p2" via="org_exam" onLeft={jest.fn()} />)
    await waitFor(() =>
      expect(screen.queryByTestId('participant-card')).not.toBeInTheDocument(),
    )
  })

  it('share join still renders with an empty cohort and collapses the box', async () => {
    mockGet.mockResolvedValue({
      tier: 'participant',
      via: 'share',
      can_leave: true,
      cannot_leave_reason: null,
    })
    const Cohort = ({ onEmpty }: any) => {
      const [rows, setRows] = useState(0)
      useEffect(() => onEmpty(rows === 0), [onEmpty, rows])
      return (
        <button data-testid="cohort-add" onClick={() => setRows(1)}>
          {rows}
        </button>
      )
    }
    registerSlot('ProjectCohortLeaderboard', Cohort)
    render(<ParticipantCard projectId="p1" via="share" onLeft={jest.fn()} />)
    expect(await screen.findByTestId('participant-leave')).toBeInTheDocument()
    const box = screen.getByTestId('participant-cohort')
    await waitFor(() => expect(box).toHaveAttribute('data-empty', 'true'))
    expect(box).toHaveClass('hidden')
    // Rows arriving later bring the box back without a remount.
    fireEvent.click(screen.getByTestId('cohort-add'))
    await waitFor(() => expect(box).toHaveAttribute('data-empty', 'false'))
    expect(box).not.toHaveClass('hidden')
    expect(screen.getByTestId('participant-card')).toBeInTheDocument()
  })

  it('attempted: explains the access, offers no leave button, hides with an empty cohort', async () => {
    mockGet.mockResolvedValue({
      tier: 'attempted',
      via: 'attempted',
      can_leave: false,
      cannot_leave_reason: 'attempted',
    })
    const Cohort = ({ projectId }: any) => (
      <div data-testid="cohort-stub">{projectId}</div>
    )
    registerSlot('ProjectCohortLeaderboard', Cohort)
    const { unmount } = render(
      <ParticipantCard projectId="p1" via="attempted" onLeft={jest.fn()} />,
    )
    expect(
      await screen.findByTestId('participant-cannot-leave'),
    ).toHaveTextContent('Abgabe')
    expect(screen.getByTestId('participant-via')).toBeInTheDocument()
    expect(screen.queryByTestId('participant-leave')).not.toBeInTheDocument()
    expect(mockLeave).not.toHaveBeenCalled()
    expect(screen.getByTestId('cohort-stub')).toHaveTextContent('p1')
    unmount()

    // Community edition (no cohort slot): nothing actionable, card hidden.
    registerSlot('ProjectCohortLeaderboard', null as any)
    render(
      <ParticipantCard projectId="p2" via="attempted" onLeft={jest.fn()} />,
    )
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith('p2'))
    await waitFor(() =>
      expect(screen.queryByTestId('participant-card')).not.toBeInTheDocument(),
    )
  })

  it('falls back to the via prop when the participation fetch fails', async () => {
    mockGet.mockRejectedValue(new Error('403'))
    render(<ParticipantCard projectId="p1" via="org_exam" onLeft={jest.fn()} />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(screen.getByTestId('participant-via')).toBeInTheDocument()
    expect(screen.queryByTestId('participant-leave')).not.toBeInTheDocument()
    expect(
      screen.queryByTestId('participant-cannot-leave'),
    ).not.toBeInTheDocument()
  })
})
