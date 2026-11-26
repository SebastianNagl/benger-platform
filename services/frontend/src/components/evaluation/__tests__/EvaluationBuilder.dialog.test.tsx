/**
 * EvaluationBuilder: creating and editing a method in the dialog.
 *
 * Covers the dialog container itself: the step navigation (which steps can
 * be opened, how many steps a metric has), saving from any step once the
 * fields are set, where an edit opens, the guard against losing unsaved
 * changes (Escape, Cancel, the close button) and the per-metric editor slot
 * rendering inside the dialog with its full prop contract.
 *
 * @jest-environment jsdom
 */

import { registerMetric, registerMetricGroup } from '@/lib/api/evaluation-types'
import { registerMetricEditor } from '@/lib/extensions/metricEditors'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import { EvaluationBuilder } from '../EvaluationBuilder'

const mockT = jest.fn((key: string, _vars?: Record<string, unknown>) => key)
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: mockT }),
}))

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({ models: [], loading: false }),
}))

jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn().mockResolvedValue({ data: {} }),
    post: jest.fn().mockResolvedValue({ data: {} }),
  },
}))

const availableFields = {
  model_response_fields: ['model_answer'],
  human_annotation_fields: [],
  all_fields: ['model_answer', 'reference'],
  reference_fields: ['reference'],
}

const bleuConfig = {
  id: 'eval-bleu',
  metric: 'bleu',
  display_name: 'BLEU',
  prediction_fields: ['model_answer'],
  reference_fields: ['reference'],
  metric_parameters: { max_order: 4 },
  enabled: true,
  created_at: '2025-01-01',
}

function renderBuilder(
  evaluations: any[] = [],
  onEvaluationsChange = jest.fn(),
) {
  render(
    <EvaluationBuilder
      projectId="project-1"
      availableFields={availableFields}
      evaluations={evaluations}
      onEvaluationsChange={onEvaluationsChange}
    />,
  )
  return onEvaluationsChange
}

const body = () => screen.getByTestId('evaluation-wizard-body')
const tickFirstField = async (user: ReturnType<typeof userEvent.setup>) =>
  user.click(within(body()).getAllByRole('checkbox')[0])

beforeAll(() => {
  // An extension-style metric: no reference, own parameter editor.
  registerMetric('dialog_ext_metric', {
    display_name: 'Dialog Extension Metric',
    description: 'test-only',
    category: 'extended',
    supports_parameters: true,
    reference_free: true,
  } as any)
  registerMetric('dialog_mount_metric', {
    display_name: 'Dialog Mount Metric',
    description: 'test-only',
    category: 'extended',
    supports_parameters: true,
    reference_free: true,
  } as any)
  registerMetricGroup({
    name: 'Dialog Extensions',
    description: 'test-only',
    metrics: ['dialog_ext_metric', 'dialog_mount_metric'],
  } as any)
})

beforeEach(() => {
  jest.clearAllMocks()
})

describe('EvaluationBuilder dialog', () => {
  it('opens a dialog for a new method on the metric step', async () => {
    const user = userEvent.setup()
    renderBuilder()

    await user.click(screen.getByTestId('add-evaluation-button'))

    const dialog = screen.getByRole('dialog')
    expect(
      within(dialog).getByText('evaluationBuilder.newEvaluation'),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText('evaluationBuilder.steps.metric.title'),
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('wizard-step-nav-metric').getAttribute('aria-current'),
    ).toBe('step')
  })

  it('lets a step be opened only once every step before it is filled in', async () => {
    const user = userEvent.setup()
    renderBuilder()
    await user.click(screen.getByTestId('add-evaluation-button'))

    // Nothing chosen yet: only the metric step is open.
    expect(
      screen.getByTestId('wizard-step-nav-prediction_fields'),
    ).toBeDisabled()
    expect(screen.getByTestId('wizard-step-nav-review')).toBeDisabled()

    await user.click(screen.getByTestId('metric-button-bleu'))
    expect(
      screen.getByTestId('wizard-step-nav-prediction_fields'),
    ).not.toBeDisabled()
    expect(
      screen.getByTestId('wizard-step-nav-reference_fields'),
    ).toBeDisabled()

    await user.click(screen.getByTestId('wizard-step-nav-prediction_fields'))
    await tickFirstField(user)
    await user.click(screen.getByTestId('wizard-step-nav-reference_fields'))
    await tickFirstField(user)

    // Every field step is set: the review can be opened directly.
    expect(screen.getByTestId('wizard-step-nav-review')).not.toBeDisabled()
    await user.click(screen.getByTestId('wizard-step-nav-review'))
    expect(screen.getByTestId('evaluation-name-input')).toBeInTheDocument()

    // Jumping back keeps what was chosen.
    await user.click(screen.getByTestId('wizard-step-nav-metric'))
    expect(screen.getByTestId('metric-button-bleu')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('counts only the steps the metric uses', async () => {
    const user = userEvent.setup()
    renderBuilder()
    await user.click(screen.getByTestId('add-evaluation-button'))
    await user.click(screen.getByTestId('metric-button-dialog_ext_metric'))

    // Reference-free: no reference step, four steps in all.
    expect(
      screen.queryByTestId('wizard-step-nav-reference_fields'),
    ).not.toBeInTheDocument()
    // "Step x of n" goes through t() with the numbers as variables.
    const stepOf = mockT.mock.calls.filter(
      ([key]) => key === 'evaluationBuilder.stepOf',
    )
    expect(stepOf[stepOf.length - 1][1]).toEqual({ current: 1, total: 4 })
  })

  it('saves from the parameters step once the fields are set', async () => {
    const user = userEvent.setup()
    const onChange = renderBuilder()
    await user.click(screen.getByTestId('add-evaluation-button'))

    await user.click(screen.getByTestId('metric-button-bleu'))
    expect(screen.getByTestId('wizard-save-early-button')).toBeDisabled()
    await user.click(screen.getByTestId('wizard-next-button'))
    await tickFirstField(user)
    await user.click(screen.getByTestId('wizard-next-button'))
    await tickFirstField(user)
    await user.click(screen.getByTestId('wizard-next-button'))

    // On the parameters step: Save is open before the review.
    await user.click(screen.getByTestId('wizard-save-early-button'))

    expect(onChange).toHaveBeenCalledTimes(1)
    const [saved] = onChange.mock.calls[0][0]
    expect(saved).toEqual(
      expect.objectContaining({
        metric: 'bleu',
        prediction_fields: ['__all_model__'],
        reference_fields: ['reference'],
        enabled: true,
      }),
    )
    expect(mockAddToast).toHaveBeenCalledWith(
      'evaluationBuilder.toast.added',
      'success',
    )
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
  })

  it('opens an edit on the parameters step with every step reachable', async () => {
    const user = userEvent.setup()
    renderBuilder([bleuConfig])

    await user.click(screen.getByTestId('evaluation-method-edit'))

    expect(
      screen.getByText('evaluationBuilder.editEvaluation'),
    ).toBeInTheDocument()
    expect(
      screen
        .getByTestId('wizard-step-nav-parameters')
        .getAttribute('aria-current'),
    ).toBe('step')
    for (const step of [
      'metric',
      'prediction_fields',
      'reference_fields',
      'review',
    ]) {
      expect(screen.getByTestId(`wizard-step-nav-${step}`)).not.toBeDisabled()
    }
  })

  it('updates the edited method in place without changing other fields', async () => {
    const user = userEvent.setup()
    const other = { ...bleuConfig, id: 'eval-other', display_name: 'Other' }
    const onChange = renderBuilder([bleuConfig, other])

    await user.click(screen.getAllByTestId('evaluation-method-edit')[0])
    await user.click(screen.getByTestId('wizard-step-nav-review'))
    await user.click(screen.getByTestId('wizard-save-button'))

    const saved = onChange.mock.calls[0][0]
    expect(saved).toHaveLength(2)
    expect(saved[0]).toEqual(
      expect.objectContaining({
        id: 'eval-bleu',
        metric: 'bleu',
        metric_parameters: { max_order: 4 },
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
      }),
    )
    expect(saved[1]).toBe(other)
  })

  it('closes on Escape at once when nothing changed', async () => {
    const user = userEvent.setup()
    renderBuilder([bleuConfig])
    await user.click(screen.getByTestId('evaluation-method-edit'))

    await user.keyboard('{Escape}')

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(
      screen.queryByText('evaluationBuilder.discard.title'),
    ).not.toBeInTheDocument()
  })

  it('asks before Escape throws away changes, and keeps them on "keep editing"', async () => {
    const user = userEvent.setup()
    const onChange = renderBuilder()
    await user.click(screen.getByTestId('add-evaluation-button'))
    await user.click(screen.getByTestId('metric-button-bleu'))

    await user.keyboard('{Escape}')
    expect(
      await screen.findByText('evaluationBuilder.discard.title'),
    ).toBeInTheDocument()

    await user.click(screen.getByText('evaluationBuilder.discard.keepEditing'))
    await waitFor(() =>
      expect(
        screen.queryByText('evaluationBuilder.discard.title'),
      ).not.toBeInTheDocument(),
    )
    // Still open, with the choice intact.
    expect(screen.getByTestId('metric-button-bleu')).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(onChange).not.toHaveBeenCalled()
  })

  it.each([
    ['Cancel', 'wizard-cancel-button'],
    ['the close button', 'evaluation-method-modal-close'],
  ])(
    'discards the changes through %s after the confirmation',
    async (_label, testId) => {
      const user = userEvent.setup()
      const onChange = renderBuilder()
      await user.click(screen.getByTestId('add-evaluation-button'))
      await user.click(screen.getByTestId('metric-button-bleu'))

      await user.click(screen.getByTestId(testId))
      await user.click(
        await screen.findByText('evaluationBuilder.discard.confirm'),
      )

      await waitFor(() =>
        expect(
          screen.queryByTestId('evaluation-method-modal'),
        ).not.toBeInTheDocument(),
      )
      expect(onChange).not.toHaveBeenCalled()

      // The next "Add" starts from scratch.
      await user.click(screen.getByTestId('add-evaluation-button'))
      expect(screen.getByTestId('metric-button-bleu')).toHaveAttribute(
        'aria-pressed',
        'false',
      )
    },
  )

  it('renders a registered metric editor inside the dialog with the full slot contract', async () => {
    const received: any[] = []
    const ExtEditor = (props: any) => {
      received.push(props)
      return (
        <button
          type="button"
          data-testid="dialog-ext-patch"
          onClick={() => props.onChange({ policy: 'strict' })}
        >
          patch
        </button>
      )
    }
    registerMetricEditor('dialog_ext_metric', ExtEditor as any)

    const user = userEvent.setup()
    const onChange = renderBuilder([bleuConfig])
    await user.click(screen.getByTestId('add-evaluation-button'))
    await user.click(screen.getByTestId('metric-button-dialog_ext_metric'))
    await user.click(screen.getByTestId('wizard-next-button'))
    await tickFirstField(user)
    await user.click(screen.getByTestId('wizard-next-button'))

    const dialog = screen.getByRole('dialog')
    await act(async () => {
      await user.click(within(dialog).getByTestId('dialog-ext-patch'))
    })

    const last = received[received.length - 1]
    expect(last.metric).toBe('dialog_ext_metric')
    expect(last.projectId).toBe('project-1')
    expect(last.parameters).toEqual({ policy: 'strict' })
    expect(last.siblingConfigs).toEqual([
      { metric: 'bleu', metric_parameters: { max_order: 4 } },
    ])

    await user.click(screen.getByTestId('wizard-next-button'))
    await user.click(screen.getByTestId('wizard-save-button'))
    expect(onChange.mock.calls[0][0][1]).toEqual(
      expect.objectContaining({
        metric: 'dialog_ext_metric',
        metric_parameters: { policy: 'strict' },
        reference_fields: [],
      }),
    )
  })
})

describe('EvaluationBuilder dialog with an editor that writes defaults on mount', () => {
  // Like an extension editor that writes its policy (or the default for a
  // missing one) back every time it mounts.
  const DefaultingEditor = (props: any) => {
    const { onChange, parameters } = props
    React.useEffect(() => {
      onChange({ policy: parameters.policy ?? 'lenient' })
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])
    return (
      <button
        type="button"
        data-testid="dialog-mount-change"
        onClick={() => onChange({ policy: 'strict' })}
      >
        {String(parameters.policy)}
      </button>
    )
  }
  const mountConfig = {
    id: 'eval-mount',
    metric: 'dialog_mount_metric',
    display_name: 'Mount',
    prediction_fields: ['model_answer'],
    reference_fields: [],
    metric_parameters: { threshold: 2 },
    enabled: true,
    created_at: '2025-01-01',
  }

  beforeAll(() => {
    registerMetricEditor('dialog_mount_metric', DefaultingEditor as any)
  })

  it.each([
    [
      'Escape',
      (user: ReturnType<typeof userEvent.setup>) => user.keyboard('{Escape}'),
    ],
    [
      'Cancel',
      (user: ReturnType<typeof userEvent.setup>) =>
        user.click(screen.getByTestId('wizard-cancel-button')),
    ],
  ])(
    'closes an untouched edit through %s without the discard prompt',
    async (_label, close) => {
      const user = userEvent.setup()
      const onChange = renderBuilder([mountConfig])
      await user.click(screen.getByTestId('evaluation-method-edit'))

      // The edit opens on the parameters step, where the default lands.
      expect(
        await screen.findByTestId('dialog-mount-change'),
      ).toHaveTextContent('lenient')

      await close(user)

      await waitFor(() =>
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
      )
      expect(
        screen.queryByText('evaluationBuilder.discard.title'),
      ).not.toBeInTheDocument()
      expect(onChange).not.toHaveBeenCalled()
    },
  )

  it('still asks once the user changes a value after the defaults', async () => {
    const user = userEvent.setup()
    renderBuilder([mountConfig])
    await user.click(screen.getByTestId('evaluation-method-edit'))
    await screen.findByText('lenient')

    await user.click(screen.getByTestId('dialog-mount-change'))
    expect(screen.getByTestId('dialog-mount-change')).toHaveTextContent(
      'strict',
    )
    await user.keyboard('{Escape}')

    expect(
      await screen.findByText('evaluationBuilder.discard.title'),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('still asks after a change when the editor mounts again on return to the parameters step', async () => {
    const user = userEvent.setup()
    renderBuilder([mountConfig])
    await user.click(screen.getByTestId('evaluation-method-edit'))
    await screen.findByText('lenient')

    await user.click(screen.getByTestId('dialog-mount-change'))
    await user.click(screen.getByTestId('wizard-step-nav-review'))
    await user.click(screen.getByTestId('wizard-step-nav-parameters'))
    expect(screen.getByTestId('dialog-mount-change')).toHaveTextContent(
      'strict',
    )

    await user.click(screen.getByTestId('wizard-cancel-button'))

    expect(
      await screen.findByText('evaluationBuilder.discard.title'),
    ).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

describe('EvaluationBuilder method list', () => {
  it('shows each method as one row with edit and delete', async () => {
    const user = userEvent.setup()
    const onChange = renderBuilder([bleuConfig])

    const row = screen.getByTestId('evaluation-method-row')
    expect(within(row).getByText('BLEU')).toBeInTheDocument()
    // No raw parameter dump in the list.
    expect(row.textContent).not.toContain('max_order')

    await user.click(within(row).getByTestId('evaluation-method-delete'))
    expect(onChange).toHaveBeenCalledWith([])
  })
})
