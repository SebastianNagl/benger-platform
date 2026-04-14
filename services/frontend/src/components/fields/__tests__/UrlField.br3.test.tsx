/**
 * @jest-environment jsdom
 *
 * Branch coverage: UrlField.tsx
 * Targets: br0[0] L17 (readonly default), br1[0] L18 (errors default)
 */

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string) => k, locale: 'de' }),
}))

import { render } from '@testing-library/react'
import React from 'react'
import { UrlField } from '../UrlField'

describe('UrlField br3', () => {
  it('renders with default readonly=false and errors=[]', () => {
    const field = {
      name: 'url',
      type: 'url' as const,
      label: 'URL',
      required: false,
    }
    const { container } = render(
      <UrlField
        field={field}
        value="https://example.com"
        onChange={jest.fn()}
      />
    )
    const input = container.querySelector('input')
    expect(input).toBeInTheDocument()
    expect(input?.readOnly).toBe(false)
  })
})
