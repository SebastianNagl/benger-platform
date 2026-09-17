/**
 * @jest-environment jsdom
 *
 * Tests for the public LMS host routes: consent (/lti/consent), the
 * existing-account step (/lti/link-account) and the mailed link
 * confirmation (/lti/link-confirm/<token>).
 *
 * Each is a thin dispatcher to an extended slot with fixed name
 * (LtiConsentGate, LtiIdentityChoice, LtiLinkConfirm). Without the extended
 * package it renders a neutral, translated notice and never crashes. The
 * routes being public and chrome-less is pinned in authRedirect.test.ts and
 * ConditionalLayout.test.tsx.
 */

import { render, screen } from '@testing-library/react'
import React from 'react'

const mockUseSlot = jest.fn()
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockUseSlot(name),
}))

const mockParams = { current: {} as Record<string, string> }
jest.mock('next/navigation', () => ({
  useParams: () => mockParams.current,
  useSearchParams: () => new URLSearchParams(),
}))

const mockLocale = { current: 'en' as 'en' | 'de' }
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, any> =
        mockLocale.current === 'de'
          ? require('../../../locales/de/common.json')
          : require('../../../locales/en/common.json')
      let value: any = translations
      for (const part of key.split('.')) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      return typeof value === 'string' ? value : key
    },
    locale: mockLocale.current,
  }),
}))

import LtiConsentPage from '../consent/page'
import LtiLinkAccountPage from '../link-account/page'
import LtiLinkConfirmPage from '../link-confirm/[token]/page'

beforeEach(() => {
  mockUseSlot.mockReset()
  mockUseSlot.mockReturnValue(null)
  mockParams.current = {}
  mockLocale.current = 'en'
})

describe.each([
  {
    route: '/lti/consent',
    Page: LtiConsentPage,
    slot: 'LtiConsentGate',
    en: 'Learning platform consent is not available in this edition.',
    de: 'Die Zustimmung für Lernplattformen ist in dieser Edition nicht verfügbar.',
  },
  {
    route: '/lti/link-account',
    Page: LtiLinkAccountPage,
    slot: 'LtiIdentityChoice',
    en: 'Linking with learning platforms is not available in this edition.',
    de: 'Das Verknüpfen mit Lernplattformen ist in dieser Edition nicht verfügbar.',
  },
  {
    route: '/lti/link-confirm/[token]',
    Page: LtiLinkConfirmPage,
    slot: 'LtiLinkConfirm',
    en: 'Confirming a learning platform link is not available in this edition.',
    de: 'Die Bestätigung einer Lernplattform-Verknüpfung ist in dieser Edition nicht verfügbar.',
  },
])('$route host route', ({ Page, slot, en, de }) => {
  it(`asks for the ${slot} slot and shows the notice without it`, () => {
    render(<Page />)
    expect(mockUseSlot).toHaveBeenCalledWith(slot)
    expect(screen.getByTestId('lti-host-fallback')).toHaveTextContent(en)
  })

  it('translates the notice', () => {
    mockLocale.current = 'de'
    render(<Page />)
    expect(screen.getByText(de)).toBeInTheDocument()
  })

  it(`renders the registered ${slot} slot instead of the notice`, () => {
    mockUseSlot.mockImplementation((name: string) =>
      name === slot ? () => <div>extended {name}</div> : null,
    )
    render(<Page />)
    expect(screen.getByText(`extended ${slot}`)).toBeInTheDocument()
    expect(screen.queryByTestId('lti-host-fallback')).not.toBeInTheDocument()
  })
})

describe('/lti/link-confirm/[token] host route', () => {
  it('hands the token from the URL to the slot', () => {
    const received: string[] = []
    mockParams.current = { token: 'tok-abc_123' }
    mockUseSlot.mockReturnValue(({ token }: { token: string }) => {
      received.push(token)
      return <div>confirm {token}</div>
    })

    render(<LtiLinkConfirmPage />)

    expect(screen.getByText('confirm tok-abc_123')).toBeInTheDocument()
    expect(received.every((token) => token === 'tok-abc_123')).toBe(true)
  })

  it('passes an empty token when the segment is missing', () => {
    mockUseSlot.mockReturnValue(({ token }: { token: string }) => (
      <div data-testid="confirm">[{token}]</div>
    ))

    render(<LtiLinkConfirmPage />)

    expect(screen.getByTestId('confirm')).toHaveTextContent('[]')
  })
})

describe('slot props', () => {
  it.each([
    ['consent', LtiConsentPage],
    ['link-account', LtiLinkAccountPage],
  ])('the %s slot reads its own query parameters (no props)', (_, Page) => {
    const received: object[] = []
    mockUseSlot.mockReturnValue((props: object) => {
      received.push(props)
      return <div>slot</div>
    })

    render(<Page />)

    expect(received.length).toBeGreaterThan(0)
    received.forEach((props) => expect(props).toEqual({}))
  })
})
