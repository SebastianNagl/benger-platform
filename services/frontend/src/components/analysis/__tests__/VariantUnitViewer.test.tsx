/**
 * The variant unit viewer: twin tasks side by side with the declared spans
 * highlighted, the factor and level pickers, the answers with their flags
 * and requests, the unit check, and the loader's refusal for viewers
 * without full content rights.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { MISSING } from '@/lib/analysis/results'
import { variantViewsAPI } from '@/lib/api/variantViews'
import {
  caseText,
  makeGeneration,
  makeTrialRequest,
  makeUnitView,
} from '@/test-utils/variantViewFixtures'
import { RequestRecordView } from '../RequestRecordView'
import { VariantUnitLoader, VariantUnitViewer } from '../VariantUnitViewer'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

jest.mock('@/lib/api/variantViews', () => ({
  variantViewsAPI: { getUnit: jest.fn(), getTrialRequest: jest.fn() },
}))

const api = variantViewsAPI as jest.Mocked<typeof variantViewsAPI>

beforeEach(() => jest.clearAllMocks())

describe('VariantUnitViewer', () => {
  it('puts twins side by side with their declared spans highlighted', () => {
    render(<VariantUnitViewer view={makeUnitView()} />)
    const reference = screen.getByTestId('unit-reference')
    const treated = screen.getByTestId('unit-treated')
    expect(within(reference).getByText('party = first')).toBeInTheDocument()
    expect(within(treated).getByText('party = second')).toBeInTheDocument()
    expect(within(reference).getByTestId('unit-span')).toHaveTextContent(
      'Ida Brook',
    )
    expect(within(treated).getByTestId('unit-span')).toHaveTextContent(
      'Olaf Penn',
    )
    expect(within(reference).getAllByTestId('unit-text')[0]).toHaveTextContent(
      caseText('first').text,
    )
    expect(within(reference).getByText('may differ', { exact: false }))
    // The free reference text and the gold value.
    expect(within(reference).getAllByText('41')).toHaveLength(2)
    expect(screen.getByTestId('unit-check-ok')).toBeInTheDocument()
    expect(screen.getByText('case: u1')).toBeInTheDocument()
    expect(screen.getByText(/Design swap \(frozen\)/)).toBeInTheDocument()
    // Two pairs along party (early and late order).
    expect(
      within(screen.getByTestId('unit-pair')).getAllByRole('option'),
    ).toHaveLength(2)
  })

  it('starts from the focus and lets the reader pick another factor and levels', async () => {
    const user = userEvent.setup()
    render(
      <VariantUnitViewer
        view={makeUnitView()}
        focus={{ factor: 'party', reference: 'second', level: 'first' }}
      />,
    )
    expect(screen.getByTestId('unit-reference')).toHaveTextContent(
      'party = second',
    )
    await user.selectOptions(screen.getByTestId('unit-factor'), 'order')
    expect(screen.getByTestId('unit-reference')).toHaveTextContent(
      'order = early',
    )
    expect(screen.getByTestId('unit-treated')).toHaveTextContent('order = late')
    await user.selectOptions(screen.getByTestId('unit-pair'), '1')
    expect(screen.getByTestId('unit-reference')).toHaveTextContent(
      'party = second',
    )
    // The same level on both sides pairs nothing: the tasks are listed.
    await user.selectOptions(screen.getByTestId('unit-treated-level'), 'early')
    expect(screen.getByTestId('unit-no-twin')).toBeInTheDocument()
    expect(screen.getAllByTestId('unit-task')).toHaveLength(4)
    await user.selectOptions(screen.getByTestId('unit-reference-level'), 'late')
    expect(screen.queryByTestId('unit-no-twin')).toBeNull()
  })

  it('lists the tasks of a design without within-unit factors', () => {
    const view = makeUnitView()
    render(
      <VariantUnitViewer
        view={{
          ...view,
          design: {
            ...view.design,
            unit_name: null,
            factors: [
              { name: 'level', type: 'numeric', varies: 'between_units' },
            ],
          },
          tasks_truncated: true,
          system: null,
        }}
      />,
    )
    expect(screen.getAllByTestId('unit-task')).toHaveLength(4)
    expect(screen.queryByTestId('unit-factor')).toBeNull()
    expect(screen.queryByTestId('unit-no-twin')).toBeNull()
    expect(screen.getByText('Unit: u1')).toBeInTheDocument()
    expect(
      screen.getByText('Only the first tasks of this unit are shown.'),
    ).toBeInTheDocument()
  })

  it('says when a task has more answers than are shown', () => {
    const view = makeUnitView()
    render(
      <VariantUnitViewer
        view={{
          ...view,
          tasks: view.tasks.map((task, i) => ({
            ...task,
            generations_truncated: i === 0,
          })),
          system: null,
        }}
      />,
    )
    expect(screen.getAllByTestId('unit-answers-truncated')).toHaveLength(1)
    expect(screen.getByTestId('unit-answers-truncated')).toHaveTextContent(
      'Only the first answers to this task are shown.',
    )
  })

  it('shows answer flags, the answer text and the request of an answer', async () => {
    const user = userEvent.setup()
    const view = makeUnitView()
    view.tasks[0].generations = [
      makeGeneration({
        id: 'g1',
        refusal: true,
        parse_status: 'failed',
        retried: true,
        fields: { share: [1, 2], detail: { a: 1 }, empty: null },
        response_truncated: true,
      }),
    ]
    view.tasks[1].generations = []
    view.tasks[0].gold = [{ name: 'reference', path: 'reference', value: null }]
    const requestView = jest.fn((g) => <p>request of {g.id}</p>)
    render(<VariantUnitViewer view={view} requestView={requestView} />)
    const reference = screen.getByTestId('unit-reference')
    expect(within(reference).getByText('Refusal')).toBeInTheDocument()
    expect(within(reference).getByText('Parse: failed')).toBeInTheDocument()
    expect(within(reference).getByText('Format retry')).toBeInTheDocument()
    expect(within(reference).getByText('1, 2')).toBeInTheDocument()
    expect(within(reference).getByText('{"a":1}')).toBeInTheDocument()
    expect(
      within(screen.getByTestId('unit-treated')).getByText(
        'No answer of this system.',
      ),
    ).toBeInTheDocument()

    await user.click(within(reference).getByText('Show the answer'))
    expect(within(reference).getByText(/\{"share": 40\}…/)).toBeInTheDocument()
    await user.click(within(reference).getByText('Hide the answer'))

    await user.click(within(reference).getByTestId('unit-answer-request'))
    expect(requestView).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'g1' }),
    )
    expect(within(reference).getByText('request of g1')).toBeInTheDocument()
    await user.click(within(reference).getByText('Hide the request'))
    expect(within(reference).queryByText('request of g1')).toBeNull()
  })

  it.each([
    ['verified', true, true, 'request-hash-ok'],
    ['mismatch', true, false, 'request-hash-mismatch'],
    ['mismatch', false, false, 'request-hash-mismatch'],
    ['record_missing', false, null, 'request-hash-unverifiable'],
  ] as const)(
    'opens the hash check of an answer (%s, object record: %s)',
    async (state, hasRecord, matches, testId) => {
      const user = userEvent.setup()
      const view = makeUnitView()
      view.tasks[0].generations = [
        makeGeneration({
          id: 'g1',
          has_request_record: hasRecord,
          hash_check: state,
        }),
      ]
      const record = makeTrialRequest().request_record
      render(
        <VariantUnitViewer
          view={view}
          requestView={(g) => (
            <RequestRecordView
              view={makeTrialRequest({
                id: g.id,
                request_record: hasRecord ? record : null,
                request_sha256: g.request_sha256,
                computed_sha256: hasRecord ? 'cd'.repeat(32) : null,
                hash_matches: matches,
                hash_check: state,
              })}
            />
          )}
        />,
      )
      const reference = screen.getByTestId('unit-reference')
      const note = within(reference).queryByTestId(
        'unit-answer-hash-unverifiable',
      )
      // Only a hash without any record is not checkable; a stored record
      // that is not an object is a mismatch, never labelled neutral.
      if (state === 'record_missing') expect(note).toBeInTheDocument()
      else expect(note).toBeNull()
      const button = within(reference).getByTestId('unit-answer-request')
      expect(button).toBeEnabled()
      await user.click(button)
      expect(within(reference).getByTestId(testId)).toBeInTheDocument()
      if (state !== 'mismatch')
        expect(
          within(reference).queryByTestId('request-hash-mismatch'),
        ).toBeNull()
    },
  )

  it('disables the request of an answer without a record and shows no values', () => {
    const view = makeUnitView()
    view.tasks[1].generations = [
      makeGeneration({
        id: 'g2',
        has_request_record: false,
        request_sha256: null,
        fields: {},
        response: '',
      }),
    ]
    render(<VariantUnitViewer view={view} requestView={() => null} />)
    const treated = screen.getByTestId('unit-treated')
    expect(within(treated).getByTestId('unit-answer-request')).toBeDisabled()
    expect(within(treated).getByText('No parsed values.')).toBeInTheDocument()
    expect(within(treated).queryByText('Show the answer')).toBeNull()
  })

  it('shows the slots of a task and folds away the fields that must match', async () => {
    const user = userEvent.setup()
    const view = makeUnitView()
    view.tasks[0].slots = [
      { index: 0, factors: { pos: 1, group: 'a' } },
      { index: 1, factors: { pos: 2 } },
    ]
    view.tasks[0].texts.push(
      {
        path: 'meta.court',
        kind: 'fixed',
        text: 'District court',
        truncated: false,
        spans: [],
      },
      {
        path: 'meta.long',
        kind: 'fixed',
        text: 'line one\nline two',
        truncated: true,
        spans: [],
      },
    )
    render(<VariantUnitViewer view={view} />)
    const reference = screen.getByTestId('unit-reference')
    const slots = within(reference).getByTestId('unit-slots')
    expect(within(slots).getAllByRole('row')).toHaveLength(3)
    expect(within(slots).getByText('group')).toBeInTheDocument()
    expect(within(slots).getAllByText(MISSING)).toHaveLength(1)
    const fixed = within(reference).getByTestId('unit-fixed-fields')
    expect(fixed).not.toHaveAttribute('open')
    await user.click(
      within(fixed).getByText('Fields that are the same across the unit (2)'),
    )
    expect(within(fixed).getByText('District court')).toBeVisible()
    expect(within(fixed).getByTestId('unit-text')).toHaveTextContent(
      'line one line two…',
    )
  })

  it('shows every field of a design that declares none that may differ', () => {
    const view = makeUnitView()
    for (const task of view.tasks) {
      task.texts = [
        {
          path: 'case',
          kind: 'fixed',
          text: 'Roster one',
          truncated: false,
          spans: [],
        },
      ]
    }
    render(<VariantUnitViewer view={view} />)
    expect(screen.queryByTestId('unit-fixed-fields')).toBeNull()
    expect(screen.getAllByTestId('unit-field')[0]).toHaveTextContent(
      'caseRoster one',
    )
  })

  it('lists the problems of the unit check', () => {
    const view = makeUnitView({
      check: {
        ok: false,
        task_count: 4,
        assignments: { ok: true, problem_count: 0, problems: [] },
        balance: {
          ok: false,
          problem_count: 1,
          problems: [{ message: 'missing cell' }],
        },
        invariance: {
          ok: false,
          problem_count: 1,
          problems: [
            {
              kind: 'text_differs_outside_spans',
              path: 'facts',
              excerpt_a: 'asks',
              excerpt_b: 'begs',
            },
          ],
        },
      },
    })
    render(<VariantUnitViewer view={view} />)
    const notice = screen.getByTestId('unit-check-problems')
    expect(notice).toHaveTextContent('2 problems in this unit')
    expect(notice).toHaveTextContent(
      'Invariance: text_differs_outside_spans (facts) · asks / begs',
    )
    expect(notice).toHaveTextContent('Balance: missing cell')
  })
})

describe('VariantUnitLoader', () => {
  it('loads a unit and opens an answer request through the trial route', async () => {
    const user = userEvent.setup()
    api.getUnit.mockResolvedValue(makeUnitView())
    api.getTrialRequest.mockResolvedValue(makeTrialRequest())
    render(
      <VariantUnitLoader
        projectId="p1"
        designKey="swap"
        unit="u1"
        system="sim-alpha"
        focus={{ factor: 'party' }}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Loading the unit…')
    const viewer = await screen.findByTestId('variant-unit-viewer')
    expect(api.getUnit).toHaveBeenCalledWith('p1', 'swap', 'u1', 'sim-alpha')
    await user.click(
      within(within(viewer).getByTestId('unit-reference')).getByTestId(
        'unit-answer-request',
      ),
    )
    expect(await screen.findByTestId('request-hash-ok')).toBeInTheDocument()
    expect(api.getTrialRequest).toHaveBeenCalledWith('g1', 'run-1')
  })

  it('refuses viewers without full content rights', async () => {
    api.getUnit.mockRejectedValue({ response: { status: 403 } })
    render(
      <VariantUnitLoader
        projectId="p1"
        designKey="swap"
        unit="u1"
        system={null}
      />,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Examples need the org admin or contributor role on the project',
    )
  })

  it('shows other load errors', async () => {
    api.getUnit.mockRejectedValueOnce(new Error('Gateway timeout'))
    const { rerender } = render(
      <VariantUnitLoader
        projectId="p1"
        designKey="swap"
        unit="u1"
        system={null}
      />,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Gateway timeout',
    )
    api.getUnit.mockRejectedValueOnce({})
    rerender(
      <VariantUnitLoader
        projectId="p1"
        designKey="swap"
        unit="u2"
        system={null}
      />,
    )
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'The unit could not be loaded.',
      ),
    )
  })
})
