/**
 * @jest-environment jsdom
 *
 * The key create form suggests a 90-day validity (still optional) and keeps
 * the request limits within the deployment maximum the scope catalog
 * reports (API_KEY_MAX_RPM / API_KEY_MAX_RPD).
 */

import type { ScopeCatalog } from '@/lib/api/types'
import { mockTranslate } from '@/test-utils/accessKeyFixtures'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: mockTranslate, locale: 'en' }),
}))

import { AccessKeyCreateForm } from '../AccessKeyCreateForm'
import { DEFAULT_EXPIRY, expiryToIso } from '../accessKeyUtils'

const DAY = 24 * 60 * 60 * 1000

const CATALOG: ScopeCatalog = {
  scopes: [
    {
      name: 'projects:read',
      description_de: 'DE',
      description_en: 'EN',
      implies: [],
      grantable: 'any',
    },
  ],
  presets: { benchmark_read: ['projects:read'] },
  limits: {
    default_per_minute: 120,
    default_per_day: 20000,
    max_per_minute: 600,
    max_per_day: 100000,
  },
}

function renderForm() {
  const onSubmit = jest.fn().mockResolvedValue(undefined)
  render(
    <AccessKeyCreateForm
      mode="personal"
      catalog={CATALOG}
      onSubmit={onSubmit}
      onCancel={jest.fn()}
    />,
  )
  fireEvent.change(screen.getByTestId('access-key-name'), {
    target: { value: 'ci' },
  })
  return onSubmit
}

describe('access key validity and limits', () => {
  it('suggests 90 days of validity', async () => {
    expect(DEFAULT_EXPIRY).toBe('90')
    const onSubmit = renderForm()
    expect(screen.getByTestId('access-key-expiry-hint')).toHaveTextContent(
      'accessKeys.form.expiryHint',
    )
    const before = Date.now()
    fireEvent.click(screen.getByTestId('access-key-create-submit'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    const expires = Date.parse(onSubmit.mock.calls[0][0].expires_at)
    expect(expires).toBeGreaterThanOrEqual(before + 90 * DAY - 1000)
    expect(expires).toBeLessThanOrEqual(Date.now() + 90 * DAY + 1000)
    expect(expiryToIso('never')).toBeNull()
  })

  it('shows the deployment limits and refuses values above the maximum', async () => {
    const onSubmit = renderForm()
    fireEvent.click(screen.getByTestId('access-key-limits-toggle'))
    expect(screen.getByTestId('access-key-rpm')).toHaveAttribute('max', '600')
    expect(screen.getByTestId('access-key-rpd')).toHaveAttribute(
      'max',
      '100000',
    )
    expect(
      screen.getByText(/accessKeys\.form\.rateLimitsRange/),
    ).toHaveTextContent('"maxPerMinute":600')

    fireEvent.change(screen.getByTestId('access-key-rpm'), {
      target: { value: '601' },
    })
    fireEvent.click(screen.getByTestId('access-key-create-submit'))
    expect(screen.getByTestId('access-key-form-error')).toHaveTextContent(
      'accessKeys.form.rateLimitTooHigh',
    )
    expect(onSubmit).not.toHaveBeenCalled()

    fireEvent.change(screen.getByTestId('access-key-rpm'), {
      target: { value: '600' },
    })
    fireEvent.click(screen.getByTestId('access-key-create-submit'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSubmit.mock.calls[0][0].rate_limit_per_minute).toBe(600)
  })
})
