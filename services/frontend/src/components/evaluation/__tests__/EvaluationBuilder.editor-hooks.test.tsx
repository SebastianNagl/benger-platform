/**
 * The draft and save hooks the builder hands a registered metric editor:
 * onDraftChange swaps the edited draft to another metric (and so to that
 * metric's editor), and onSaveTransform changes the whole method list when
 * the dialog saves.
 *
 * @jest-environment jsdom
 */

import type { EvaluationConfig } from '@/lib/api/evaluation-types'
import { registerMetric, registerMetricGroup } from '@/lib/api/evaluation-types'
import {
  type MetricEditorProps,
  registerMetricEditor,
} from '@/lib/extensions/metricEditors'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvaluationBuilder } from '../EvaluationBuilder'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
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

const method = (id: string, metric: string): EvaluationConfig => ({
  id,
  metric,
  display_name: id,
  metric_parameters: { origin: id },
  prediction_fields: ['model_answer'],
  reference_fields: ['reference'],
  enabled: true,
})

// The editor for the first metric offers both hooks; the second only shows
// which parameters it was given.
function SourceEditor({ onDraftChange, onSaveTransform }: MetricEditorProps) {
  return (
    <div data-testid="source-editor">
      <button
        onClick={() =>
          onDraftChange?.({
            metric: 'hooks_target_metric',
            metric_parameters: { mode: 'switched' },
          })
        }
      >
        swap
      </button>
      <button
        onClick={() =>
          onSaveTransform?.((configs) =>
            configs.filter((c) => c.id !== 'other'),
          )
        }
      >
        drop-other
      </button>
    </div>
  )
}

function TargetEditor({ parameters }: MetricEditorProps) {
  return <div data-testid="target-editor">{JSON.stringify(parameters)}</div>
}

beforeAll(() => {
  const baseDef = {
    description: 'editor hook test metric',
    category: 'extended',
    supports_parameters: true,
  }
  registerMetric('hooks_source_metric', {
    ...baseDef,
    display_name: 'Hooks Source',
  } as any)
  registerMetric('hooks_target_metric', {
    ...baseDef,
    display_name: 'Hooks Target',
  } as any)
  registerMetricGroup({
    name: 'Editor Hook Tests',
    description: 'Test-only extension metrics',
    metrics: ['hooks_source_metric', 'hooks_target_metric'],
  } as any)
  registerMetricEditor('hooks_source_metric', SourceEditor)
  registerMetricEditor('hooks_target_metric', TargetEditor)
})

function setup() {
  const onEvaluationsChange = jest.fn()
  const evaluations = [
    method('edited', 'hooks_source_metric'),
    method('other', 'hooks_source_metric'),
  ]
  render(
    <EvaluationBuilder
      projectId="p1"
      availableFields={availableFields}
      evaluations={evaluations}
      onEvaluationsChange={onEvaluationsChange}
    />,
  )
  const savedList = (): EvaluationConfig[] =>
    onEvaluationsChange.mock.calls.at(-1)[0]
  return { onEvaluationsChange, savedList }
}

// Editing a method with fields set opens on its parameters step.
const editFirst = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getAllByTestId('evaluation-method-edit')[0])

describe('metric editor draft and save hooks', () => {
  it('onDraftChange swaps the draft to the other metric and its editor', async () => {
    const user = userEvent.setup()
    const { savedList } = setup()
    await editFirst(user)
    expect(screen.getByTestId('source-editor')).toBeInTheDocument()

    await user.click(screen.getByText('swap'))

    expect(screen.queryByTestId('source-editor')).not.toBeInTheDocument()
    expect(screen.getByTestId('target-editor')).toHaveTextContent(
      '{"mode":"switched"}',
    )

    await user.click(screen.getByTestId('wizard-save-early-button'))
    const edited = savedList().find((c) => c.id === 'edited')!
    expect(edited.metric).toBe('hooks_target_metric')
    expect(edited.metric_parameters).toEqual({ mode: 'switched' })
    // The swap named no display_name, so the method keeps its own.
    expect(edited.display_name).toBe('edited')
  })

  it('applies a registered save transform to the method list', async () => {
    const user = userEvent.setup()
    const { savedList } = setup()
    await editFirst(user)

    await user.click(screen.getByText('drop-other'))
    await user.click(screen.getByTestId('wizard-save-early-button'))

    expect(savedList().map((c) => c.id)).toEqual(['edited'])
  })

  it('drops the transform when the dialog is cancelled', async () => {
    const user = userEvent.setup()
    const { onEvaluationsChange, savedList } = setup()
    await editFirst(user)
    await user.click(screen.getByText('drop-other'))
    await user.click(screen.getByTestId('wizard-cancel-button'))
    expect(onEvaluationsChange).not.toHaveBeenCalled()

    await editFirst(user)
    await user.click(screen.getByTestId('wizard-save-early-button'))

    expect(savedList().map((c) => c.id)).toEqual(['edited', 'other'])
  })

  it('drops the transform when the user picks another metric', async () => {
    const user = userEvent.setup()
    const { savedList } = setup()
    await editFirst(user)
    await user.click(screen.getByText('drop-other'))

    await user.click(screen.getByTestId('wizard-step-nav-metric'))
    await user.click(screen.getByTestId('metric-button-hooks_target_metric'))
    await user.click(screen.getByTestId('wizard-save-early-button'))

    const saved = savedList()
    expect(saved.map((c) => c.id)).toEqual(['edited', 'other'])
    expect(saved.find((c) => c.id === 'edited')!.metric).toBe(
      'hooks_target_metric',
    )
    expect(saved[1]).toEqual(method('other', 'hooks_source_metric'))
  })

  it('saves only the edited method when no transform is registered', async () => {
    const user = userEvent.setup()
    const { savedList } = setup()
    await editFirst(user)
    await user.click(screen.getByTestId('wizard-save-early-button'))

    const saved = savedList()
    expect(saved.map((c) => c.id)).toEqual(['edited', 'other'])
    expect(saved[1]).toEqual(method('other', 'hooks_source_metric'))
  })
})
