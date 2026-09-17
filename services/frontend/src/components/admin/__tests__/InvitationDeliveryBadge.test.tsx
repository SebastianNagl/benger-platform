import { render, screen } from '@testing-library/react'

import type { InvitationDetails } from '@/lib/api/invitations'
import { InvitationDeliveryBadge } from '../InvitationDeliveryBadge'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

type Delivery = Pick<
  InvitationDetails,
  | 'email_status'
  | 'email_sent_at'
  | 'email_last_attempt_at'
  | 'email_attempts'
  | 'email_last_error'
>

const render_ = (invitation: Delivery) =>
  render(<InvitationDeliveryBadge invitation={invitation} />)

describe('InvitationDeliveryBadge', () => {
  it('shows the sent state once the provider accepted the mail', () => {
    render_({
      email_status: 'sent',
      email_sent_at: '2026-09-17T08:00:00Z',
      email_attempts: 1,
    })

    expect(screen.getByTestId('invitation-delivery-sent')).toBeInTheDocument()
    expect(
      screen.getByText('admin.invitationDelivery.status.sent'),
    ).toBeInTheDocument()
  })

  it('shows the failure and puts the provider error in the tooltip', () => {
    render_({
      email_status: 'failed',
      email_last_attempt_at: '2026-09-17T08:00:00Z',
      email_attempts: 3,
      email_last_error: 'SendGrid 400: does not contain a valid address',
    })

    const badge = screen.getByTestId('invitation-delivery-failed')
    expect(badge.getAttribute('title')).toContain('valid address')
    expect(badge.getAttribute('title')).toContain(
      'admin.invitationDelivery.attempts: 3',
    )
  })

  it('distinguishes queued from sent', () => {
    // A queued mail is what the old UI called "invite sent". Conflating the
    // two is the bug this badge exists to fix.
    render_({
      email_status: 'queued',
      email_last_attempt_at: '2026-09-17T08:00:00Z',
      email_attempts: 0,
    })

    expect(screen.getByTestId('invitation-delivery-queued')).toBeInTheDocument()
    expect(
      screen.queryByTestId('invitation-delivery-sent'),
    ).not.toBeInTheDocument()
  })

  it('falls back to unknown for invitations from before the bookkeeping', () => {
    // Pre-migration rows carry no timestamps. Reporting them as failed would
    // cry wolf on every historical invitation.
    render_({})

    expect(
      screen.getByTestId('invitation-delivery-unknown'),
    ).toBeInTheDocument()
    expect(
      screen.queryByTestId('invitation-delivery-failed'),
    ).not.toBeInTheDocument()
  })

  it('omits an attempt count of zero from the tooltip', () => {
    render_({ email_status: 'queued', email_attempts: 0 })

    expect(
      screen.getByTestId('invitation-delivery-queued').getAttribute('title'),
    ).not.toContain('admin.invitationDelivery.attempts')
  })
})
