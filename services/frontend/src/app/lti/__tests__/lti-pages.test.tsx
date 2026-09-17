/**
 * @jest-environment jsdom
 *
 * Tests for the LTI host routes (link picker, launch error).
 *
 * The link host is a thin slot dispatcher: without the extended package it
 * must render a graceful community fallback and never crash. The error host
 * differs: its fallback is a working, translated page that explains every
 * launch error code, says who can fix it and shows the support reference,
 * because launches can fail on a community install too. The public consent
 * and account-linking hosts are covered in lti-public-pages.test.tsx.
 */

import { render, screen } from '@testing-library/react'
import React from 'react'

const mockUseSlot = jest.fn()
jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockUseSlot(name),
}))

const mockSearchParams = { current: new URLSearchParams() }
jest.mock('next/navigation', () => ({
  useSearchParams: () => mockSearchParams.current,
}))

// Resolve keys against the real locale files, so the test sees the copy a
// user sees (the global mock returns the bare key).
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

import {
  LTI_ERROR_ACTIONS,
  LTI_LAUNCH_ERROR_CODES,
  type LtiErrorAction,
} from '@/lib/lti/launchErrors'
import deCommon from '@/locales/de/common.json'
import enCommon from '@/locales/en/common.json'

import LtiErrorPage from '../error/page'
import LtiLinkPage from '../link/page'

beforeEach(() => {
  mockUseSlot.mockReset()
  mockUseSlot.mockReturnValue(null)
  mockSearchParams.current = new URLSearchParams()
  mockLocale.current = 'en'
})

describe('LTI link host route', () => {
  it('renders the community fallback when no slot is registered', () => {
    render(<LtiLinkPage />)
    expect(mockUseSlot).toHaveBeenCalledWith('LtiLinkPicker')
    expect(
      screen.getByText('LTI content linking requires the extended edition.'),
    ).toBeInTheDocument()
  })

  it('renders the registered LtiLinkPicker slot', () => {
    mockUseSlot.mockReturnValue(() => <div>extended link picker</div>)
    render(<LtiLinkPage />)
    expect(screen.getByText('extended link picker')).toBeInTheDocument()
    expect(
      screen.queryByText('LTI content linking requires the extended edition.'),
    ).not.toBeInTheDocument()
  })
})

describe('LTI error host route', () => {
  const COPY = { en: enCommon.lti.error, de: deCommon.lti.error }
  const EN = COPY.en

  function renderWith(query: string, locale: 'en' | 'de' = 'en') {
    mockSearchParams.current = new URLSearchParams(query)
    mockLocale.current = locale
    return render(<LtiErrorPage />)
  }

  function actionIds(): string[] {
    return Array.from(
      screen.getByTestId('lti-error-actions').querySelectorAll('li'),
    ).map((li) => li.getAttribute('data-testid') ?? '')
  }

  it('requests the LtiLaunchError slot and prefers it when registered', () => {
    mockUseSlot.mockReturnValue(() => <div>extended error view</div>)
    render(<LtiErrorPage />)
    expect(mockUseSlot).toHaveBeenCalledWith('LtiLaunchError')
    expect(screen.getByText('extended error view')).toBeInTheDocument()
    expect(screen.queryByTestId('lti-error-fallback')).not.toBeInTheDocument()
    expect(screen.queryByText(EN.title)).not.toBeInTheDocument()
  })

  it('has one distinct message per code in both languages', () => {
    for (const locale of ['en', 'de'] as const) {
      const codes = COPY[locale].codes as Record<string, string>
      expect(Object.keys(codes).sort()).toEqual(
        [...LTI_LAUNCH_ERROR_CODES].sort(),
      )
      const messages = LTI_LAUNCH_ERROR_CODES.map((code) => codes[code])
      expect(new Set(messages).size).toBe(messages.length)
      expect(messages).not.toContain(COPY[locale].default)
    }
  })

  it.each([...LTI_LAUNCH_ERROR_CODES])(
    'explains %s and lists who can fix it',
    (code) => {
      renderWith(`code=${code}`)
      expect(
        screen.getByRole('heading', { level: 1, name: EN.title }),
      ).toBeInTheDocument()
      expect(screen.getByTestId('lti-error-message')).toHaveTextContent(
        (EN.codes as Record<string, string>)[code],
      )
      expect(actionIds()).toEqual(
        LTI_ERROR_ACTIONS[code].map((a) => `lti-error-action-${a}`),
      )
      for (const action of LTI_ERROR_ACTIONS[code]) {
        expect(
          screen.getByTestId(`lti-error-action-${action}`),
        ).toHaveTextContent(EN.actions[action])
      }
      expect(screen.getByTestId('lti-error-code')).toHaveTextContent(
        `${EN.codeLabel}: ${code}`,
      )
      // No raw translation key reaches the page.
      expect(document.body.textContent).not.toMatch(/lti\.error\./)
    },
  )

  it.each([...LTI_LAUNCH_ERROR_CODES])('renders %s in German', (code) => {
    renderWith(`code=${code}`, 'de')
    const de = COPY.de
    expect(
      screen.getByRole('heading', { level: 1, name: de.title }),
    ).toBeInTheDocument()
    expect(screen.getByText(de.actionsTitle)).toBeInTheDocument()
    expect(screen.getByTestId('lti-error-message')).toHaveTextContent(
      (de.codes as Record<string, string>)[code],
    )
    expect(screen.getByTestId('lti-error-code')).toHaveTextContent(
      `${de.codeLabel}: ${code}`,
    )
    expect(document.body.textContent).not.toMatch(/lti\.error\./)
  })

  it('explains not_linked in teacher terms without a staff hint', () => {
    renderWith('code=not_linked')
    expect(
      screen.getByText('This activity is not linked to an exam yet.'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('lti-error-action-teacher')).toBeInTheDocument()
    expect(
      screen.queryByTestId('lti-error-student-hint'),
    ).not.toBeInTheDocument()
  })

  it('does not blame the browser or cookies for a temporary server problem', () => {
    for (const locale of ['en', 'de'] as const) {
      const { unmount } = renderWith('code=state_unavailable', locale)
      expect(document.body.textContent).not.toMatch(/cookie/i)
      expect(actionIds()).toEqual(['lti-error-action-tryLater'])
      unmount()
    }
    renderWith('code=state_unavailable')
    expect(screen.getByText(/not caused by your browser/)).toBeInTheDocument()
    expect(screen.getByText(/temporary server problem/)).toBeInTheDocument()
  })

  it('says an invalid state is an old or reused sign-in', () => {
    renderWith('code=invalid_state')
    expect(screen.getByTestId('lti-error-message')).toHaveTextContent(
      /older than 5 minutes or was already used/,
    )
    expect(actionIds()).toEqual(['lti-error-action-reopen'])
  })

  it('names the organization admin for a switched-off connection', () => {
    renderWith('code=registration_disabled', 'de')
    expect(screen.getByTestId('lti-error-message')).toHaveTextContent(
      'Die Organisation hat die Anbindung dieser Lernplattform abgeschaltet.',
    )
    expect(screen.getByTestId('lti-error-action-orgAdmin')).toHaveTextContent(
      'Admins der Organisation',
    )
    // Students are told to go through their teachers first.
    expect(screen.getByTestId('lti-error-student-hint')).toHaveTextContent(
      COPY.de.studentHint,
    )
  })

  it('names the learning platform administration for an unknown deployment', () => {
    renderWith('code=unknown_deployment')
    expect(actionIds()).toEqual([
      'lti-error-action-lmsAdmin',
      'lti-error-action-orgAdmin',
    ])
    expect(screen.getByTestId('lti-error-student-hint')).toBeInTheDocument()
  })

  it('shows the support reference of an internal error', () => {
    renderWith('code=internal&ref=1a2b3c4d')
    expect(screen.getByTestId('lti-error-message')).toHaveTextContent(
      EN.codes.internal,
    )
    expect(screen.getByTestId('lti-error-ref')).toHaveTextContent(
      `${EN.refLabel}: 1a2b3c4d`,
    )
    // The action points at the code and reference lines below it.
    expect(screen.getByTestId('lti-error-action-tryLater')).toHaveTextContent(
      /details below/,
    )
    const action = screen.getByTestId('lti-error-actions')
    const ref = screen.getByTestId('lti-error-ref')
    const code = screen.getByTestId('lti-error-code')
    expect(
      action.compareDocumentPosition(code) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      code.compareDocumentPosition(ref) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('shows the reference in German too', () => {
    renderWith('code=internal&ref=deadbeef', 'de')
    expect(screen.getByTestId('lti-error-ref')).toHaveTextContent(
      'Referenz: deadbeef',
    )
  })

  it('leaves out the reference line without a reference', () => {
    renderWith('code=internal')
    expect(screen.queryByTestId('lti-error-ref')).not.toBeInTheDocument()
  })

  it.each(['call 0800 support', '<b>x</b>', 'zz-not-hex', 'a'.repeat(40)])(
    'does not repeat a malformed reference (%s)',
    (ref) => {
      renderWith(`code=internal&ref=${encodeURIComponent(ref)}`)
      expect(screen.queryByTestId('lti-error-ref')).not.toBeInTheDocument()
      expect(document.body.textContent).not.toContain(ref)
    },
  )

  it('falls back to the generic message and reopening for unknown codes', () => {
    renderWith('code=some_future_code')
    expect(screen.getByTestId('lti-error-message')).toHaveTextContent(
      EN.default,
    )
    expect(actionIds()).toEqual(['lti-error-action-reopen'])
    expect(screen.getByTestId('lti-error-code')).toHaveTextContent(
      `${EN.codeLabel}: some_future_code`,
    )
  })

  it('does not repeat a malformed code', () => {
    const code = 'Please call +49 123'
    renderWith(`code=${encodeURIComponent(code)}`)
    expect(screen.getByTestId('lti-error-message')).toHaveTextContent(
      EN.default,
    )
    expect(screen.queryByTestId('lti-error-code')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain(code)
  })

  it('renders the generic message and no code line when ?code= is absent', () => {
    renderWith('')
    expect(screen.getByTestId('lti-error-message')).toHaveTextContent(
      EN.default,
    )
    expect(actionIds()).toEqual(['lti-error-action-reopen'])
    expect(screen.queryByTestId('lti-error-code')).not.toBeInTheDocument()
    expect(screen.queryByTestId('lti-error-ref')).not.toBeInTheDocument()
  })

  it('has copy for every action category in both languages', () => {
    const categories: LtiErrorAction[] = [
      'reopen',
      'tryLater',
      'teacher',
      'orgAdmin',
      'lmsAdmin',
      'support',
    ]
    for (const locale of ['en', 'de'] as const) {
      expect(Object.keys(COPY[locale].actions).sort()).toEqual(
        [...categories].sort(),
      )
    }
  })
})
