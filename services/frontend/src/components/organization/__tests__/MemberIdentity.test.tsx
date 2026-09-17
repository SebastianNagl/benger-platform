/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import {
  LmsMemberBadge,
  MemberEmail,
  memberOptionLabel,
} from '../MemberIdentity'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) =>
      ({
        'admin.organizations.memberPrivacy.lmsBadge': 'LMS',
        'admin.organizations.memberPrivacy.lmsBadgeTitle':
          'Account from a learning platform (LTI)',
        'admin.organizations.memberPrivacy.pseudonymTitle':
          'You see the pseudonym.',
        'admin.organizations.memberPrivacy.emailHidden': 'Email hidden',
      })[key] ?? key,
  }),
}))

describe('LmsMemberBadge', () => {
  it('renders nothing for ordinary accounts', () => {
    const { container } = render(<LmsMemberBadge is_lms_account={false} />)
    expect(container).toBeEmptyDOMElement()
    const { container: missing } = render(<LmsMemberBadge />)
    expect(missing).toBeEmptyDOMElement()
  })

  it('explains the pseudonym on a masked row', () => {
    render(
      <LmsMemberBadge is_lms_account is_pseudonymized data-testid="badge" />,
    )
    const badge = screen.getByTestId('badge')
    expect(badge).toHaveTextContent('LMS')
    expect(badge).toHaveAttribute('title', 'You see the pseudonym.')
  })

  it('names the source on a row with a visible real name', () => {
    render(<LmsMemberBadge is_lms_account data-testid="badge" />)
    expect(screen.getByTestId('badge')).toHaveAttribute(
      'title',
      'Account from a learning platform (LTI)',
    )
  })
})

describe('MemberEmail', () => {
  it('shows the address when there is one', () => {
    render(<MemberEmail email="erika@uni.example" hidden />)
    expect(screen.getByText('erika@uni.example')).toBeInTheDocument()
  })

  it('shows a note when the address is withheld', () => {
    render(<MemberEmail email={null} hidden />)
    const note = screen.getByText('Email hidden')
    expect(note).toHaveAttribute('title', 'You see the pseudonym.')
  })

  it('renders nothing when there is no address and nothing is withheld', () => {
    const { container } = render(<MemberEmail email={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('memberOptionLabel', () => {
  it('adds the email when present', () => {
    expect(memberOptionLabel('Anna', 'anna@example.com')).toBe(
      'Anna (anna@example.com)',
    )
  })

  it('leaves out a missing email', () => {
    expect(memberOptionLabel('Kluge Eule', null)).toBe('Kluge Eule')
    expect(memberOptionLabel('Kluge Eule', undefined)).toBe('Kluge Eule')
  })

  it('never prints a missing name', () => {
    expect(memberOptionLabel(undefined, 'a@b.example')).toBe('a@b.example')
    expect(memberOptionLabel(null, null)).toBe('')
  })
})
