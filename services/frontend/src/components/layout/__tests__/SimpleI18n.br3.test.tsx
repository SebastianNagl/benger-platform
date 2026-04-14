/**
 * @jest-environment jsdom
 *
 * Branch coverage: SimpleI18n.tsx
 * Target: br3[1] L72 - changeLocale sets localStorage
 */

import { act, render } from '@testing-library/react'
import React from 'react'
import { SimpleI18nProvider, useI18n } from '../SimpleI18n'

function TestConsumer() {
  const { locale, changeLocale } = useI18n()
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <button onClick={() => changeLocale('de')}>Switch</button>
    </div>
  )
}

describe('SimpleI18n br3', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('changeLocale stores in localStorage', () => {
    const { getByText } = render(
      <SimpleI18nProvider>
        <TestConsumer />
      </SimpleI18nProvider>
    )

    act(() => {
      getByText('Switch').click()
    })

    expect(localStorage.getItem('locale')).toBe('de')
  })
})
