/**
 * @jest-environment jsdom
 *
 * The Agreement and validity block of the statistics panel: the codes of an
 * analysis run with the validations they accepted (the stored kappa and
 * per-category metrics, read from the validation), the validations of the
 * project's answers, and the agreement between LLM judges for metrics.
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'

let mockLocale: 'de' | 'en' | 'fr' = 'en'
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock(() => mockLocale),
)

jest.mock('@/lib/featureFlags', () =>
  jest.requireActual('@/test-utils/featureFlagsMock').featureFlagsMockModule(),
)

jest.mock('@/lib/api/coding', () => ({
  ...jest.requireActual('@/lib/api/coding'),
  codingAPI: {
    getValidation: jest.fn(),
    listAnswerValidations: jest.fn(),
  },
}))

import { codingAPI } from '@/lib/api/coding'
import { makeEstimates, makeRun } from '@/test-utils/analysisFixtures'
import {
  makeCodeRecord,
  makeValidationDetail,
  makeValidationSummary,
  PATTERN_HASH,
  VALIDATION_METRICS,
} from '@/test-utils/codingFixtures'
import { setMockFeatureFlags } from '@/test-utils/featureFlagsMock'
import { StatisticalResultsPanel } from '../StatisticalResultsPanel'
import {
  JudgeAgreementBlock,
  RunAgreementBlock,
  runCodes,
} from '../statistics/AgreementValidity'

const mockGet = codingAPI.getValidation as jest.Mock
const mockList = codingAPI.listAnswerValidations as jest.Mock

const exploratory = makeCodeRecord({
  measure: 'mentions_court',
  ref: 'court@1:any',
  hash: '0'.repeat(64),
  validation: undefined,
  confirmatory_estimands: undefined,
})

beforeEach(() => {
  mockLocale = 'en'
  mockGet.mockReset()
  mockList.mockReset()
  mockGet.mockResolvedValue(makeValidationDetail())
  mockList.mockResolvedValue({
    items: [
      makeValidationSummary(),
      makeValidationSummary({
        id: 'val-2',
        name: 'judge side',
        code_kind: 'judge_code',
        code_ref: 'judge-model@s1:side',
        status: 'running',
        kappa: null,
        observed_agreement: null,
        n_compared: null,
      }),
    ],
    total: 2,
  })
})

describe('RunAgreementBlock', () => {
  it('shows no block for a run without codes and reads nothing', () => {
    const { container, rerender } = render(
      <RunAgreementBlock run={makeRun()} />,
    )
    expect(container).toBeEmptyDOMElement()
    rerender(<RunAgreementBlock run={makeRun({ codes: [] })} />)
    expect(container).toBeEmptyDOMElement()
    rerender(<RunAgreementBlock run={makeRun({ codes: null })} />)
    expect(container).toBeEmptyDOMElement()
    expect(mockGet).not.toHaveBeenCalled()
    expect(mockList).not.toHaveBeenCalled()
  })

  it('shows each code with the stored kappa and per-category metrics of its validation', async () => {
    render(
      <RunAgreementBlock
        run={makeRun({ codes: [makeCodeRecord(), exploratory] })}
      />,
    )
    const block = screen.getByTestId('agreement-validity-block')
    expect(
      within(block).getByText('Agreement and validity'),
    ).toBeInTheDocument()
    expect(within(block).getByText('Codes of this run (2)')).toBeInTheDocument()
    const [validated, notValidated] = screen.getAllByTestId('run-code')
    expect(within(validated).getByText('blames_claimant')).toBeInTheDocument()
    expect(within(validated).getByText('Text pattern')).toBeInTheDocument()
    expect(within(validated).getByText('Validated')).toBeInTheDocument()
    expect(within(validated).getByText('blame@1:claimant')).toBeInTheDocument()
    expect(within(validated).getByTitle(PATTERN_HASH)).toHaveTextContent(
      PATTERN_HASH.slice(0, 12),
    )
    expect(within(validated).getByText('1 of 10 rows')).toBeInTheDocument()
    expect(within(validated).getByText('blame_effect')).toBeInTheDocument()
    // What the run recorded, before the detail arrives.
    expect(validated).toHaveTextContent(
      'Validated on the control side: kappa 0.59, agreement 77.8 %, 9 items compared',
    )
    expect(
      within(validated).getByRole('link', { name: 'Open coding project' }),
    ).toHaveAttribute('href', '/projects/coding-1')

    expect(mockGet).toHaveBeenCalledWith('val-1')
    const kappa = await within(validated).findByTestId('validation-kappa')
    expect(kappa).toHaveTextContent('0.59')
    expect(kappa).toHaveTextContent('moderate')
    expect(
      within(validated).getByTestId('validation-observed'),
    ).toHaveTextContent('77.8 %')
    expect(
      within(validated).getByTestId('validation-expected'),
    ).toHaveTextContent('45.7 %')
    expect(
      within(validated).getByTestId('validation-compared'),
    ).toHaveTextContent('9of 10 items')
    const rows = within(validated).getAllByTestId('validation-category-row')
    expect(rows.map((r) => r.textContent)).toEqual([
      '(missing)00.00--',
      'D41.000.750.86',
      'P50.800.800.80',
    ])
    const per = VALIDATION_METRICS.automatic_vs_reference.per_category!
    expect(per.D.f1).toBeCloseTo(0.857, 3)
    expect(validated).toHaveTextContent(
      '1 item whose human codes tie has no reference and is left out.',
    )
    expect(validated).toHaveTextContent(
      '1 item without an automatic code counts as the category (missing).',
    )
    expect(
      within(validated).getByTestId('validation-between-coders'),
    ).toHaveTextContent(
      "Between the 2 human coders on the 1 item coded by two or more: Fleiss' kappa -1.00",
    )

    expect(within(notValidated).getByText('Not validated')).toBeInTheDocument()
    expect(
      within(notValidated).queryByTestId('code-validation-agreement'),
    ).not.toBeInTheDocument()
  })

  it('keeps the recorded numbers when the reader cannot open the validation', async () => {
    mockGet.mockRejectedValue({ response: { status: 404 } })
    render(<RunAgreementBlock run={makeRun({ codes: [makeCodeRecord()] })} />)
    expect(
      await screen.findByTestId('validation-detail-unavailable'),
    ).toHaveTextContent('You cannot open the coding project')
    expect(screen.getByTestId('run-code')).toHaveTextContent('kappa 0.59')
    expect(screen.queryByTestId('validation-kappa')).not.toBeInTheDocument()
  })

  it('says the validation could not be loaded on any other error', async () => {
    mockGet.mockRejectedValue({ response: { status: 500 } })
    const warn = jest.spyOn(console, 'warn').mockImplementation(() => {})
    render(<RunAgreementBlock run={makeRun({ codes: [makeCodeRecord()] })} />)
    expect(
      await screen.findByTestId('validation-detail-failed'),
    ).toHaveTextContent('The validation could not be loaded')
    expect(
      screen.queryByTestId('validation-detail-unavailable'),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId('run-code')).toHaveTextContent('kappa 0.59')
    warn.mockRestore()
  })

  it('reads every page of the project validations and counts what it lists', async () => {
    const page = (n: number, from: number) =>
      Array.from({ length: n }, (_, i) =>
        makeValidationSummary({
          id: `val-${from + i + 1}`,
          name: `v${from + i}`,
        }),
      )
    mockList.mockImplementation(
      (_project: string, limit: number, offset: number) =>
        Promise.resolve({
          items: offset === 0 ? page(limit, 0) : page(3, offset),
          total: 203,
        }),
    )
    render(<RunAgreementBlock run={makeRun({ codes: [makeCodeRecord()] })} />)
    const list = await screen.findByTestId('project-code-validations')
    expect(mockList.mock.calls).toEqual([
      ['project-1', 200, 0],
      ['project-1', 200, 200],
    ])
    expect(
      within(list).getByText("Validations of this project's answers (203)"),
    ).toBeInTheDocument()
    expect(within(list).getAllByTestId('project-code-validation')).toHaveLength(
      203,
    )
  })

  it('lists the validations of the project answers and marks the ones the run used', async () => {
    render(<RunAgreementBlock run={makeRun({ codes: [makeCodeRecord()] })} />)
    const list = await screen.findByTestId('project-code-validations')
    expect(mockList).toHaveBeenCalledWith('project-1', 200, 0)
    expect(
      within(list).getByText("Validations of this project's answers (2)"),
    ).toBeInTheDocument()
    const [used, other] = within(list).getAllByTestId('project-code-validation')
    expect(within(used).getByText('used by this run')).toBeInTheDocument()
    expect(
      within(used).getByRole('link', { name: 'Coding: side' }),
    ).toHaveAttribute('href', '/projects/coding-1')
    expect(used).toHaveTextContent('Completed')
    expect(used).toHaveTextContent('0.59')
    expect(
      within(other).queryByText('used by this run'),
    ).not.toBeInTheDocument()
    expect(other).toHaveTextContent('Judge code')
    expect(other).toHaveTextContent('Running')
  })

  it('hides the project list when the project has no validations', async () => {
    mockList.mockResolvedValue({ items: [], total: 0 })
    render(<RunAgreementBlock run={makeRun({ codes: [makeCodeRecord()] })} />)
    await waitFor(() => expect(mockList).toHaveBeenCalled())
    await screen.findByTestId('validation-kappa')
    expect(
      screen.queryByTestId('project-code-validations'),
    ).not.toBeInTheDocument()
  })

  it('speaks German', async () => {
    mockLocale = 'de'
    render(<RunAgreementBlock run={makeRun({ codes: [makeCodeRecord()] })} />)
    expect(
      screen.getByText('Übereinstimmung und Validität'),
    ).toBeInTheDocument()
    expect(await screen.findByTestId('validation-kappa')).toHaveTextContent(
      '0,59',
    )
  })

  it('runCodes keeps only records with a measure', () => {
    expect(
      runCodes(
        makeRun({ codes: [makeCodeRecord(), {} as never, null as never] }),
      ),
    ).toHaveLength(1)
  })
})

describe('StatisticalResultsPanel', () => {
  // The Agreement and validity block belongs to variant_experiments.
  beforeEach(() => setMockFeatureFlags({ variant_experiments: true }))

  it('shows the block under Inference and Fit only for a run with codes', async () => {
    const { rerender } = render(
      <StatisticalResultsPanel
        data={null}
        analysis={{ run: makeRun(), estimates: makeEstimates() }}
      />,
    )
    expect(screen.getByTestId('analysis-fit-block')).toBeInTheDocument()
    expect(
      screen.queryByTestId('agreement-validity-block'),
    ).not.toBeInTheDocument()
    rerender(
      <StatisticalResultsPanel
        data={null}
        analysis={{
          run: makeRun({ codes: [makeCodeRecord()] }),
          estimates: makeEstimates(),
        }}
      />,
    )
    expect(screen.getByTestId('agreement-validity-block')).toBeInTheDocument()
    await screen.findByTestId('validation-kappa')
  })

  it('shows no judge agreement while variant_experiments is off', () => {
    setMockFeatureFlags({})
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'model',
          metrics: {},
          judge_agreement_by_model_metric: {
            'model-a|cfg-1|llm_judge_custom': {
              n_judges: 2,
              n_items: 12,
              fleiss_kappa: null,
              cohens_kappa_pairwise: {},
              pearson_r_pairwise: { 'judge-x__judge-y': 0.91 },
              percent_agreement: 0.5,
              mean_absolute_deviation: 0.12,
            },
          },
        }}
      />,
    )
    expect(screen.queryByTestId('judge-agreement-block')).toBeNull()
  })

  it('shows judge agreement in the same block for metrics', () => {
    render(
      <StatisticalResultsPanel
        data={{
          aggregation: 'model',
          metrics: {},
          judge_agreement_by_model_metric: {
            'model-a|cfg-1|llm_judge_custom': {
              n_judges: 2,
              n_items: 12,
              fleiss_kappa: null,
              cohens_kappa_pairwise: {},
              pearson_r_pairwise: { 'judge-x__judge-y': 0.91 },
              percent_agreement: 0.5,
              mean_absolute_deviation: 0.12,
            },
          },
        }}
      />,
    )
    const block = screen.getByTestId('judge-agreement-block')
    expect(
      within(block).getByText('Agreement and validity'),
    ).toBeInTheDocument()
    const row = within(block).getByTestId('judge-agreement-row')
    expect(row).toHaveTextContent('model-a')
    expect(row).toHaveTextContent('llm_judge_custom · cfg-1')
    expect(row).toHaveTextContent('judge-x / judge-y: r = 0.91')
    expect(row).toHaveTextContent('50.0 %')
    expect(row).toHaveTextContent('0.12')
  })
})

describe('JudgeAgreementBlock', () => {
  it('renders nothing without a judge pair', () => {
    const { container, rerender } = render(
      <JudgeAgreementBlock agreement={null} />,
    )
    expect(container).toBeEmptyDOMElement()
    rerender(
      <JudgeAgreementBlock
        agreement={{ 'm|metric': { n_judges: 1, n_items: 3 } }}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('reads two-part keys and kappa pairs', () => {
    render(
      <JudgeAgreementBlock
        agreement={{
          'model-a|passed': {
            n_judges: 3,
            n_items: 8,
            fleiss_kappa: 0.42,
            cohens_kappa_pairwise: { j1__j2: 0.4 },
          },
        }}
      />,
    )
    const row = screen.getByTestId('judge-agreement-row')
    expect(row).toHaveTextContent('passed')
    expect(row).toHaveTextContent('j1 / j2: κ = 0.40')
    expect(row).toHaveTextContent('0.42')
  })
})

describe('codeLabel', () => {
  const { codeLabel } = jest.requireActual(
    '@/components/evaluation/CodeValidationAgreement',
  )
  const t = (key: string, vars?: Record<string, string | number>) =>
    `${key}:${vars?.version}`
  it('adds the version only when the ref does not name it', () => {
    expect(codeLabel('set@2:code', '2', t)).toBe('set@2:code')
    expect(codeLabel('coder:out', '0.3', t)).toBe(
      'coder:out (evaluation.agreementValidity.version:0.3)',
    )
    expect(codeLabel('judge:side', null, t)).toBe('judge:side')
    expect(codeLabel(null, null, t)).toBe('-')
    expect(codeLabel(null, '1', t)).toBe(
      'evaluation.agreementValidity.version:1',
    )
  })
})
