/**
 * @jest-environment jsdom
 *
 * AnnotatorAgreement (presentation) and AnnotatorAgreementCard (the
 * evaluations page block that loads it and hides itself without overlap).
 */
import '@testing-library/jest-dom'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'

let mockLocale: 'de' | 'en' | 'fr' = 'en'
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock(() => mockLocale),
)

jest.mock('@/lib/api/agreement', () => ({
  ...jest.requireActual('@/lib/api/agreement'),
  getAnnotatorAgreement: jest.fn(),
}))

import { getAnnotatorAgreement } from '@/lib/api/agreement'
import { AGREEMENT_FIXTURE } from '@/test-utils/agreementFixture'
import { AnnotatorAgreement, kappaBand } from '../AnnotatorAgreement'
import { AnnotatorAgreementCard } from '../AnnotatorAgreementCard'

const mockGet = getAnnotatorAgreement as jest.Mock

beforeEach(() => {
  mockLocale = 'en'
  mockGet.mockReset()
})

describe('kappaBand', () => {
  it.each([
    [-0.1, 'poor'],
    [0, 'slight'],
    [0.2, 'fair'],
    [0.4, 'moderate'],
    [0.6, 'substantial'],
    [0.8, 'almostPerfect'],
    [1, 'almostPerfect'],
  ])('%s is %s', (kappa, band) => {
    expect(kappaBand(kappa)).toBe(band)
  })
})

describe('AnnotatorAgreement', () => {
  it('shows kappa, its band and percent agreement for a choices control', () => {
    render(<AnnotatorAgreement agreement={AGREEMENT_FIXTURE} />)
    expect(screen.getByTestId('annotator-agreement')).toHaveTextContent(
      '4 tasks were annotated by two or more people (3 annotators).',
    )
    const label = screen.getByTestId('agreement-control-label')
    expect(label).toHaveTextContent('Choices · 4 tasks · 3 annotators')
    expect(within(label).getByTestId('agreement-fleiss')).toHaveTextContent(
      "Fleiss' kappa0.33fair",
    )
    expect(within(label).getByTestId('agreement-cohen')).toHaveTextContent(
      '0.40moderate',
    )
    expect(within(label).getByTestId('agreement-percent')).toHaveTextContent(
      '50.0 %',
    )
    expect(within(label).queryByTestId('agreement-pearson')).toBeNull()
  })

  it('lists annotator pairs in a collapsible table', () => {
    render(<AnnotatorAgreement agreement={AGREEMENT_FIXTURE} />)
    const label = screen.getByTestId('agreement-control-label')
    fireEvent.click(within(label).getByText('Annotator pairs (3)'))
    const rows = within(label).getAllByRole('row')
    expect(rows).toHaveLength(4) // header + 3 pairs
    expect(rows[2]).toHaveTextContent('AshCedar40.20')
  })

  it('shows Pearson and mean absolute deviation for a number control', () => {
    render(<AnnotatorAgreement agreement={AGREEMENT_FIXTURE} />)
    const score = screen.getByTestId('agreement-control-score')
    expect(score).toHaveTextContent('Number · 4 tasks · 2 annotators')
    expect(within(score).getByTestId('agreement-pearson')).toHaveTextContent(
      '1.00',
    )
    expect(within(score).getByTestId('agreement-mad')).toHaveTextContent('0.50')
    expect(within(score).queryByTestId('agreement-fleiss')).toBeNull()
  })

  it('names unscored controls, multi-select and truncated pairs', () => {
    const many = {
      ...AGREEMENT_FIXTURE,
      controls: [
        {
          ...AGREEMENT_FIXTURE.controls[0],
          multi_select: true,
          pairs_total: 80,
        },
      ],
    }
    render(<AnnotatorAgreement agreement={many} />)
    expect(screen.getByText(/Not scored .*: comment\./)).toBeInTheDocument()
    expect(
      screen.getByText(
        /two annotations agree only when they picked the same set/,
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Showing the 3 pairs with the most shared tasks of 80.'),
    ).toBeInTheDocument()
  })

  it('formats numbers and copy in German', () => {
    mockLocale = 'de'
    render(<AnnotatorAgreement agreement={AGREEMENT_FIXTURE} />)
    const label = screen.getByTestId('agreement-control-label')
    expect(label).toHaveTextContent('Auswahl · 4 Aufgaben · 3 Annotierende')
    expect(within(label).getByTestId('agreement-fleiss')).toHaveTextContent(
      'Fleiss-Kappa0,33ausreichend',
    )
    expect(within(label).getByTestId('agreement-percent')).toHaveTextContent(
      '50,0 %',
    )
  })
})

describe('AnnotatorAgreementCard', () => {
  it('renders the block when tasks overlap', async () => {
    mockGet.mockResolvedValue({ available: true, ...AGREEMENT_FIXTURE })
    render(<AnnotatorAgreementCard projectId="p-1" />)
    expect(
      await screen.findByTestId('annotator-agreement-card'),
    ).toHaveTextContent('Annotator agreement')
    expect(mockGet).toHaveBeenCalledWith('p-1')
  })

  it('renders nothing when no task has two annotators', async () => {
    mockGet.mockResolvedValue({ available: false, controls: [] })
    const { container } = render(<AnnotatorAgreementCard projectId="p-1" />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    await Promise.resolve()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when only unscored controls overlap', async () => {
    mockGet.mockResolvedValue({
      available: true,
      overlap_task_count: 2,
      annotator_count: 2,
      controls: [],
      unsupported_controls: [{ control: 'comment', type: 'textarea' }],
    })
    const { container } = render(<AnnotatorAgreementCard projectId="p-1" />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    await Promise.resolve()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the read fails', async () => {
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {})
    mockGet.mockRejectedValue(new Error('boom'))
    const { container } = render(<AnnotatorAgreementCard projectId="p-1" />)
    await waitFor(() => expect(warn).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
    warn.mockRestore()
  })
})
