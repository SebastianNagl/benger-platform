/**
 * @jest-environment jsdom
 */

/**
 * The builder's field steps name roles and bulk selectors in the reader's
 * language. They showed English ("model", "reference", "All model
 * responses") on German pages.
 */

import { render, screen } from '@testing-library/react'
import { PredictionFieldsStep } from '../PredictionFieldsStep'
import { ReferenceFieldsStep } from '../ReferenceFieldsStep'
import { ReviewStep } from '../ReviewStep'

const mockGerman: Record<string, string> = {
  'evaluationBuilder.fields.model': 'Modell',
  'evaluationBuilder.fields.human': 'Mensch',
  'evaluationBuilder.fields.reference': 'Referenz',
  'evaluationBuilder.fields.allModelResponses': 'Alle Modellantworten',
  'evaluationBuilder.fields.allHumanAnnotations':
    'Alle menschlichen Annotationen',
}

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => mockGerman[key] ?? key }),
}))

describe('builder field labels', () => {
  it('names the roles of prediction fields in German', () => {
    render(
      <PredictionFieldsStep
        availableFields={{
          model_response_fields: ['antwort'],
          human_annotation_fields: ['loesung'],
          reference_fields: ['task.musterloesung'],
        }}
        allPredictionOptions={[
          {
            value: '__all_model__',
            label: 'Alle Modellantworten',
            type: 'special',
          },
          { value: 'model:antwort', label: 'model:antwort', type: 'model' },
          { value: 'human:loesung', label: 'human:loesung', type: 'human' },
        ]}
        selectedFields={[]}
        onFieldToggle={jest.fn()}
      />,
    )
    expect(screen.getByText('Modell')).toBeInTheDocument()
    expect(screen.getByText('Mensch')).toBeInTheDocument()
    expect(screen.queryByText('model')).not.toBeInTheDocument()
    expect(screen.queryByText('human')).not.toBeInTheDocument()
  })

  it('names reference fields in German', () => {
    render(
      <ReferenceFieldsStep
        referenceOptions={[
          { value: 'task.musterloesung', label: 'task.musterloesung' },
        ]}
        selectedFields={[]}
        onFieldToggle={jest.fn()}
      />,
    )
    expect(screen.getByText('Referenz')).toBeInTheDocument()
    expect(screen.queryByText('reference')).not.toBeInTheDocument()
  })

  it('translates bulk selectors on the review step and keeps field names', () => {
    render(
      <ReviewStep
        metric="llm_judge_classic"
        predictionFields={['__all_model__', 'human:loesung']}
        referenceFields={['task.musterloesung']}
        metricParameters={{}}
      />,
    )
    expect(screen.getByText('Alle Modellantworten')).toBeInTheDocument()
    expect(screen.queryByText('All model responses')).not.toBeInTheDocument()
    expect(screen.getByText('human:loesung')).toBeInTheDocument()
  })
})
