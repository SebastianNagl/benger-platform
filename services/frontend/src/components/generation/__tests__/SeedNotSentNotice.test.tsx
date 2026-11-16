/**
 * A run whose requested seed did not reach the model says so instead of only
 * showing `"seed": null` in its parameters (Kolibri-1 benchmark, K3).
 */

import { translateKey } from '@/lib/i18n/catalog'
import { render, screen } from '@testing-library/react'
import { SeedNotSentNotice, seedNotSentOf } from '../SeedNotSentNotice'

// t() resolves against the real English catalog.
const mockT = (key: string, vars?: Record<string, unknown>) =>
  translateKey('en', key, vars as any)

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: mockT, locale: 'en' }),
}))

describe('seedNotSentOf', () => {
  it('reads the record from the parameters', () => {
    expect(
      seedNotSentOf({ seed: null, seed_not_sent: { requested: 42 } }),
    ).toEqual({ requested: 42 })
  })

  it.each([null, undefined, {}, { seed: 42 }, { seed_not_sent: 'yes' }])(
    'is null for %p',
    (parameters) => {
      expect(seedNotSentOf(parameters as any)).toBeNull()
    },
  )
})

describe('SeedNotSentNotice', () => {
  it('names the requested seed and the catalog reason', () => {
    render(
      <SeedNotSentNotice
        parameters={{
          seed: null,
          seed_not_sent: { requested: 7, reason: 'unsupported_by_model' },
        }}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent(
      'Seed 7 was not sent: this model does not accept a seed, so its answers were generated without one.',
    )
  })

  it('names the custom-model declaration', () => {
    render(
      <SeedNotSentNotice
        parameters={{
          seed_not_sent: { requested: 42, reason: 'declared_unsupported' },
        }}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent(
      'parameter_constraints.seed.supported is false',
    )
  })

  it('renders nothing when the seed was sent', () => {
    const { container } = render(
      <SeedNotSentNotice parameters={{ seed: 42 }} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
