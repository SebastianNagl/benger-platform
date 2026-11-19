/**
 * The spec form under the start dialog and the plan editor: JSON that does
 * not parse, the engine's problems on validation, a failure without
 * problems, the starting spec with the project's designs, and the run start
 * with a trimmed name.
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import {
  AnalysisSpecForm,
  NewAnalysisRunForm,
  starterSpec,
} from '@/components/analysis/NewAnalysisRunForm'
import { makeRun } from '@/test-utils/analysisFixtures'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockValidate = jest.fn()
const mockStart = jest.fn()
jest.mock('@/lib/api/analysis', () => ({
  ...jest.requireActual('@/lib/api/analysis'),
  analysisAPI: {
    validateSpec: (...a: unknown[]) => mockValidate(...a),
    startRun: (...a: unknown[]) => mockStart(...a),
  },
}))

const specBox = () =>
  screen.getByLabelText('Analysis spec (JSON)') as HTMLTextAreaElement
const type = (value: string) =>
  fireEvent.change(specBox(), { target: { value } })

beforeEach(() => {
  jest.clearAllMocks()
})

describe('AnalysisSpecForm', () => {
  const onSubmit = jest.fn()
  const renderForm = (props = {}) =>
    render(
      <AnalysisSpecForm
        designKeys={['role_swap', 'docket']}
        nameLabel="Plan name"
        submitLabel="Save plan"
        submittingLabel="Saving"
        failedMessage="The plan could not be saved."
        onSubmit={onSubmit}
        {...props}
      />,
    )

  it('names JSON that does not parse without calling the engine', async () => {
    renderForm()
    type('{"spec_version": ')
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Not valid JSON')
    expect(mockValidate).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('lists every problem the engine names', async () => {
    mockValidate.mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail: {
            code: 'invalid_analysis_spec',
            errors: ['/estimands: must be a list', '/name: required'],
          },
        },
      },
    })
    renderForm()
    type('{}')
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    const errors = await screen.findByTestId('new-analysis-run-errors')
    expect(errors).toHaveTextContent('/estimands: must be a list')
    expect(errors).toHaveTextContent('/name: required')
  })

  it('shows a failure without problems, or the fallback message', async () => {
    mockValidate.mockRejectedValue(new Error('Network down'))
    renderForm()
    type('{}')
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Network down')

    onSubmit.mockRejectedValue({})
    fireEvent.change(screen.getByLabelText('Plan name'), {
      target: { value: 'P' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save plan' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The plan could not be saved.',
    )
  })

  it('inserts a starting spec with the designs and the name', () => {
    renderForm()
    fireEvent.change(screen.getByLabelText('Plan name'), {
      target: { value: 'Main' },
    })
    fireEvent.click(screen.getByText('Insert a starting spec'))
    const inserted = JSON.parse(specBox().value)
    expect(inserted.spec_version).toBe(1)
    expect(inserted.name).toBe('Main')
    expect(inserted.inputs.designs).toEqual(['role_swap', 'docket'])
  })

  it('submits the parsed spec and the trimmed name', async () => {
    onSubmit.mockResolvedValue(undefined)
    renderForm({ nameRequired: true })
    type('{"spec_version": 1}')
    const save = screen.getByRole('button', { name: 'Save plan' })
    expect(save).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Plan name'), {
      target: { value: '  Main ' },
    })
    fireEvent.click(save)
    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({ spec_version: 1 }, 'Main'),
    )
    await waitFor(() => expect(save).not.toBeDisabled())
  })
})

describe('starterSpec', () => {
  it('names a placeholder design when the project has none', () => {
    expect(JSON.parse(starterSpec([], 'A')).inputs.designs).toEqual([
      '<design key>',
    ])
  })
})

describe('NewAnalysisRunForm', () => {
  it('starts a run and hands it to the host', async () => {
    const run = makeRun({ id: 'run-2' })
    mockStart.mockResolvedValue(run)
    const onStarted = jest.fn()
    render(
      <NewAnalysisRunForm
        projectId="project-1"
        initialSpec='{"spec_version": 1}'
        initialName="First"
        designKeys={[]}
        onStarted={onStarted}
      />,
    )
    fireEvent.click(screen.getByTestId('new-analysis-run-start'))
    await waitFor(() => expect(onStarted).toHaveBeenCalledWith(run))
    expect(mockStart).toHaveBeenCalledWith(
      'project-1',
      { spec_version: 1 },
      'First',
    )
  })
})
