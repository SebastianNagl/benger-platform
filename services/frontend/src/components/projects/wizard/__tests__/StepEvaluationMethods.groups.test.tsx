/**
 * @jest-environment jsdom
 *
 * StepEvaluationMethods - the prediction-field picker heads its options by
 * role. The human and the model option for one field share a name, so in a
 * flat list only a prefix told them apart. This suite renders the real
 * HeadlessUI Select, because the shared Jest mock renders no headings.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import type { EvaluationConfig } from '@/lib/api/evaluation-types'
import { StepEvaluationMethods } from '../StepEvaluationMethods'

jest.mock('@/components/shared/Select', () =>
  jest.requireActual('../../../shared/Select'),
)

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, def?: any) => (typeof def === 'string' ? def : key),
  }),
}))

jest.mock('@/lib/extensions/slots', () => ({
  useSlot: () => null,
  getSlot: () => null,
  hasSlot: () => false,
  registerSlot: jest.fn(),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({ models: [{ id: 'gpt-5-mini', name: 'GPT-5 Mini' }] }),
}))

function renderExpandedRouge() {
  const onEvaluationConfigsChange = jest.fn()
  const cfg: EvaluationConfig = {
    id: 'rouge-1',
    metric: 'rouge',
    prediction_fields: ['__all_model__'],
    reference_fields: ['musterloesung'],
    enabled: true,
  }
  render(
    <StepEvaluationMethods
      evaluationConfigs={[cfg]}
      onEvaluationConfigsChange={onEvaluationConfigsChange}
      immediateEvaluationEnabled={false}
      onImmediateEvaluationChange={jest.fn()}
      annotationFields={[{ name: 'loesung', type: 'TextArea' } as any]}
      dataColumns={['musterloesung']}
      selectedModelIds={[]}
    />,
  )
  const row = screen.getByTestId('wizard-metric-rouge')
  fireEvent.click(within(row).getByRole('button'))
  return { onEvaluationConfigsChange }
}

async function openPredictionPicker(user: ReturnType<typeof userEvent.setup>) {
  const label = screen.getByText(
    'projects.creation.wizard.step7.predictionField',
  )
  await user.click(
    within(label.parentElement as HTMLElement).getByRole('button'),
  )
  return screen.getByRole('listbox')
}

describe('StepEvaluationMethods: prediction picker headings', () => {
  it('heads the bulk, model and human options, each option under its own heading', async () => {
    const user = userEvent.setup()
    renderExpandedRouge()
    const listbox = await openPredictionPicker(user)

    const sequence = Array.from(
      listbox.querySelectorAll('[role="presentation"], [role="option"]'),
    ).map((el) =>
      el.getAttribute('role') === 'option'
        ? `option ${el.getAttribute('data-value')}`
        : `heading ${el.textContent}`,
    )
    expect(sequence).toEqual([
      'heading Bulk Selection',
      'option __all_model__',
      'option __all_human__',
      'heading Model Response Fields',
      'option model:loesung',
      'heading Human Annotation Fields',
      'option human:loesung',
    ])
  })

  it('stores the human selector when the option under the human heading is picked', async () => {
    const user = userEvent.setup()
    const { onEvaluationConfigsChange } = renderExpandedRouge()
    const listbox = await openPredictionPicker(user)

    await user.click(
      within(listbox).getByRole('option', { name: 'loesung (TextArea)' }),
    )

    const configs = onEvaluationConfigsChange.mock.calls.at(-1)![0]
    expect(configs[0].prediction_fields).toEqual(['human:loesung'])
  })
})
