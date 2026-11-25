/**
 * @jest-environment jsdom
 *
 * ItemStepper: previous / next icon buttons with accessible names and an
 * "x of y" counter, disabled at the ends, in a default and a compact variant.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'

import { ItemStepper } from '../ItemStepper'

let mockLocale: 'de' | 'en' | 'fr' = 'de'
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock(() => mockLocale),
)

beforeEach(() => {
  mockLocale = 'de'
})

function setup(props: Partial<React.ComponentProps<typeof ItemStepper>> = {}) {
  const onPrevious = jest.fn()
  const onNext = jest.fn()
  render(
    <ItemStepper
      index={1}
      total={3}
      onPrevious={onPrevious}
      onNext={onNext}
      {...props}
    />,
  )
  return { onPrevious, onNext }
}

describe('ItemStepper', () => {
  it('names its buttons and counts the position', () => {
    const { onPrevious, onNext } = setup()
    expect(screen.getByTestId('item-stepper-position')).toHaveTextContent(
      '2 von 3',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Vorheriger Eintrag' }))
    fireEvent.click(screen.getByRole('button', { name: 'Nächster Eintrag' }))
    expect(onPrevious).toHaveBeenCalledTimes(1)
    expect(onNext).toHaveBeenCalledTimes(1)
  })

  it.each([
    ['en', '2 of 3', 'Previous item', 'Next item'],
    ['fr', '2 sur 3', 'Élément précédent', 'Élément suivant'],
  ] as const)('speaks %s', (locale, counter, previous, next) => {
    mockLocale = locale
    setup()
    expect(screen.getByTestId('item-stepper-position')).toHaveTextContent(
      counter,
    )
    expect(screen.getByRole('button', { name: previous })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: next })).toBeInTheDocument()
  })

  it('disables previous on the first and next on the last item', () => {
    const { onPrevious } = setup({ index: 0 })
    const previous = screen.getByTestId('item-stepper-previous')
    expect(previous).toBeDisabled()
    expect(screen.getByTestId('item-stepper-next')).toBeEnabled()
    fireEvent.click(previous)
    expect(onPrevious).not.toHaveBeenCalled()
  })

  it('disables next on the last item', () => {
    setup({ index: 2 })
    expect(screen.getByTestId('item-stepper-previous')).toBeEnabled()
    expect(screen.getByTestId('item-stepper-next')).toBeDisabled()
  })

  it('disables both and shows no count when no item is current', () => {
    setup({ index: -1 })
    expect(screen.getByTestId('item-stepper-previous')).toBeDisabled()
    expect(screen.getByTestId('item-stepper-next')).toBeDisabled()
    expect(screen.getByTestId('item-stepper-position')).toBeEmptyDOMElement()
  })

  it('disables both while disabled is set', () => {
    setup({ disabled: true })
    expect(screen.getByTestId('item-stepper-previous')).toBeDisabled()
    expect(screen.getByTestId('item-stepper-next')).toBeDisabled()
  })

  it('takes labels that say what is being stepped through', () => {
    setup({ labels: { previous: 'Vorherige Bewertung', next: 'Nächste' } })
    expect(
      screen.getByRole('button', { name: 'Vorherige Bewertung' }),
    ).toHaveAttribute('title', 'Vorherige Bewertung')
    expect(screen.getByRole('button', { name: 'Nächste' })).toBeInTheDocument()
  })

  it('renders bare chevrons in the compact variant, with the children between', () => {
    setup({
      variant: 'compact',
      testId: 'queue',
      children: <span>Abgabe 2 / 3</span>,
    })
    const previous = screen.getByTestId('queue-previous')
    expect(previous).toHaveAccessibleName('Vorheriger Eintrag')
    expect(previous).not.toHaveClass('ring-1')
    expect(previous.nextElementSibling).toHaveTextContent('Abgabe 2 / 3')
    expect(screen.queryByTestId('queue-position')).not.toBeInTheDocument()
    expect(screen.getByTestId('queue-next')).toHaveAccessibleName(
      'Nächster Eintrag',
    )
  })

  it('counts in the compact variant too', () => {
    setup({ variant: 'compact', index: 0, total: 1 })
    expect(screen.getByTestId('item-stepper-position')).toHaveTextContent(
      '1 von 1',
    )
    expect(screen.getByTestId('item-stepper-previous')).toBeDisabled()
    expect(screen.getByTestId('item-stepper-next')).toBeDisabled()
  })
})
