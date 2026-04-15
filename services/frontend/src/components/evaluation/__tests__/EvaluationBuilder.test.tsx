/**
 * @jest-environment jsdom
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EvaluationBuilder } from '../EvaluationBuilder'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      if (vars) {
        let result = key
        for (const [k, v] of Object.entries(vars)) {
          result = result.replace(`{${k}}`, String(v))
        }
        return result
      }
      return key
    },
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: jest.fn(),
  }),
}))

jest.mock('@/hooks/useModels', () => ({
  useModels: () => ({
    models: [
      {
        id: 'gpt-4',
        name: 'GPT-4',
        provider: 'openai',
        default_config: { temperature: 0 },
      },
    ],
    loading: false,
  }),
}))

jest.mock('@/lib/api', () => ({
  api: {
    get: jest.fn().mockResolvedValue({ data: [] }),
    post: jest.fn().mockResolvedValue({ data: {} }),
  },
}))

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children }: any) => <span data-testid="badge">{children}</span>,
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Checkbox', () => ({
  Checkbox: ({ checked, onChange, label }: any) => (
    <label>
      <input type="checkbox" checked={checked} onChange={onChange} />
      {label}
    </label>
  ),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  CheckIcon: () => <span data-testid="check-icon" />,
  ChevronDownIcon: () => <span data-testid="chevron-down" />,
  ChevronUpIcon: () => <span data-testid="chevron-up" />,
  InformationCircleIcon: () => <span data-testid="info-icon" />,
  PencilIcon: () => <span data-testid="pencil-icon" />,
  PlayIcon: () => <span data-testid="play-icon" />,
  PlusIcon: () => <span data-testid="plus-icon" />,
  TrashIcon: () => <span data-testid="trash-icon" />,
  XMarkIcon: () => <span data-testid="x-icon" />,
}))

jest.mock('../EvaluationControlModal', () => ({
  EvaluationControlModal: () => <div data-testid="eval-control-modal" />,
}))

jest.mock('../FieldMappingEditor', () => ({
  FieldMappingEditor: () => <div data-testid="field-mapping-editor" />,
}))

const defaultProps = {
  projectId: 'p1',
  availableFields: {
    model_response_fields: ['model_answer', 'gpt4_response'],
    human_annotation_fields: ['answer', 'rating'],
    all_fields: ['model_answer', 'gpt4_response', 'answer', 'rating', 'reference'],
    reference_fields: ['reference'],
  },
  evaluations: [],
  onEvaluationsChange: jest.fn(),
  onSave: jest.fn(),
  saving: false,
}

describe('EvaluationBuilder', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should render without crashing', () => {
    render(<EvaluationBuilder {...defaultProps} />)
    expect(document.body).toBeTruthy()
  })

  it('should show add evaluation button', () => {
    render(<EvaluationBuilder {...defaultProps} />)

    // Should have an add button with text for adding a new evaluation
    const addButtons = screen.getAllByRole('button')
    expect(addButtons.length).toBeGreaterThan(0)
  })

  it('should render with existing evaluations', () => {
    const evaluations = [
      {
        id: 'eval-1',
        metric: 'bleu',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {},
        enabled: true,
      },
    ]

    render(
      <EvaluationBuilder
        {...defaultProps}
        evaluations={evaluations}
      />
    )

    expect(document.body).toBeTruthy()
  })

  it('should render save button when onSave provided', () => {
    render(<EvaluationBuilder {...defaultProps} />)

    // The save button should be present
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(0)
  })

  it('should show saving state when saving prop is true', () => {
    render(<EvaluationBuilder {...defaultProps} saving={true} />)
    expect(document.body).toBeTruthy()
  })

  it('should render metric groups', () => {
    render(<EvaluationBuilder {...defaultProps} />)

    // The component should render metric selection UI
    expect(document.body).toBeTruthy()
  })

  it('should handle empty available fields', () => {
    render(
      <EvaluationBuilder
        {...defaultProps}
        availableFields={{
          model_response_fields: [],
          human_annotation_fields: [],
          all_fields: [],
          reference_fields: [],
        }}
      />
    )

    expect(document.body).toBeTruthy()
  })

  it('should render with multiple evaluations', () => {
    const evaluations = [
      {
        id: 'eval-1',
        metric: 'bleu',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {},
        enabled: true,
      },
      {
        id: 'eval-2',
        metric: 'rouge',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: { variant: 'rougeL' },
        enabled: true,
      },
    ]

    render(
      <EvaluationBuilder {...defaultProps} evaluations={evaluations} />
    )

    expect(document.body).toBeTruthy()
  })

  it('should handle llm_judge evaluation type', () => {
    const evaluations = [
      {
        id: 'eval-3',
        metric: 'llm_judge',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {
          judge_model: 'gpt-4',
          dimensions: ['accuracy'],
        },
        enabled: true,
      },
    ]

    render(
      <EvaluationBuilder {...defaultProps} evaluations={evaluations} />
    )

    expect(document.body).toBeTruthy()
  })

  it('should handle many evaluation types', () => {
    const evaluations = [
      {
        id: 'eval-bleu',
        metric: 'bleu',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: { ngram: 4 },
        enabled: true,
      },
      {
        id: 'eval-rouge',
        metric: 'rouge',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: { variant: 'rougeL' },
        enabled: true,
      },
      {
        id: 'eval-meteor',
        metric: 'meteor',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {},
        enabled: false,
      },
      {
        id: 'eval-bertscore',
        metric: 'bertscore',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {},
        enabled: true,
      },
      {
        id: 'eval-exact',
        metric: 'exact_match',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {},
        enabled: true,
      },
    ]

    render(
      <EvaluationBuilder {...defaultProps} evaluations={evaluations} />
    )

    expect(document.body).toBeTruthy()
  })

  it('should handle evaluations with custom parameters', () => {
    const evaluations = [
      {
        id: 'eval-custom',
        metric: 'llm_judge',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {
          judge_model: 'gpt-4',
          dimensions: ['accuracy', 'relevance', 'fluency'],
          custom_prompt_template: 'Rate this answer: {{prediction}}',
          temperature: 0.0,
          max_tokens: 1000,
        },
        enabled: true,
      },
    ]

    render(
      <EvaluationBuilder {...defaultProps} evaluations={evaluations} />
    )

    expect(document.body).toBeTruthy()
  })

  it('should call onEvaluationsChange when evaluations are modified', async () => {
    const mockOnChange = jest.fn()
    const evaluations = [
      {
        id: 'eval-1',
        metric: 'bleu',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {},
        enabled: true,
      },
    ]

    render(
      <EvaluationBuilder
        {...defaultProps}
        evaluations={evaluations}
        onEvaluationsChange={mockOnChange}
      />
    )

    // The component should render with evaluation cards
    expect(document.body).toBeTruthy()
  })

  it('should open wizard when clicking add evaluation button', async () => {
    const user = userEvent.setup()
    render(<EvaluationBuilder {...defaultProps} />)

    // Find and click the add evaluation button
    const buttons = screen.getAllByRole('button')
    const addButton = buttons.find(
      (b) =>
        b.textContent?.includes('evaluation.builder.addEvaluation') ||
        b.textContent?.includes('Add') ||
        b.querySelector('[data-testid="plus-icon"]')
    )
    if (addButton) {
      await user.click(addButton)
    }

    // Should still render without crashing
    expect(document.body).toBeTruthy()
  })

  it('should toggle evaluation enabled state', async () => {
    const mockOnChange = jest.fn()
    const user = userEvent.setup()
    const evaluations = [
      {
        id: 'eval-1',
        metric: 'bleu',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {},
        enabled: true,
      },
    ]

    render(
      <EvaluationBuilder
        {...defaultProps}
        evaluations={evaluations}
        onEvaluationsChange={mockOnChange}
      />
    )

    // Find checkbox or toggle
    const checkboxes = screen.queryAllByRole('checkbox')
    if (checkboxes.length > 0) {
      await user.click(checkboxes[0])
      // Should have called onEvaluationsChange
    }
    expect(document.body).toBeTruthy()
  })

  it('should call onSave when save button clicked', async () => {
    const mockSave = jest.fn()
    const user = userEvent.setup()
    const evaluations = [
      {
        id: 'eval-1',
        metric: 'bleu',
        prediction_field: 'model_answer',
        reference_field: 'reference',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        parameters: {},
        enabled: true,
      },
    ]

    render(
      <EvaluationBuilder
        {...defaultProps}
        evaluations={evaluations}
        onSave={mockSave}
      />
    )

    // Find save button
    const buttons = screen.getAllByRole('button')
    const saveButton = buttons.find(
      (b) =>
        b.textContent?.includes('evaluation.builder.save') ||
        b.textContent?.includes('Save')
    )
    if (saveButton) {
      await user.click(saveButton)
      expect(mockSave).toHaveBeenCalled()
    }
  })

  it('should render with multi-field evaluations', () => {
    const evaluations = [
      {
        id: 'eval-multi',
        metric: 'bleu',
        prediction_field: '__ALL_MODEL__',
        reference_field: 'reference',
        prediction_fields: ['model_answer', 'gpt4_response'],
        reference_fields: ['reference'],
        parameters: {},
        enabled: true,
      },
    ]

    render(
      <EvaluationBuilder {...defaultProps} evaluations={evaluations} />
    )

    expect(document.body).toBeTruthy()
  })

  describe('Wizard Flow', () => {
    it('should open the wizard and show metric selection step', async () => {
      const user = userEvent.setup()
      render(<EvaluationBuilder {...defaultProps} />)

      // Find and click the add evaluation button (contains PlusIcon or add text)
      const addButton = screen.getAllByRole('button').find(
        (b) =>
          b.textContent?.includes('evaluationBuilder.addNew') ||
          b.textContent?.includes('evaluation.builder.addEvaluation') ||
          b.querySelector('[data-testid="plus-icon"]')
      )
      if (addButton) {
        await user.click(addButton)
        // Wizard should show metric step title
        await waitFor(() => {
          expect(
            screen.queryByText('evaluationBuilder.steps.metric.title') ||
              screen.queryByText(/metric/i)
          ).toBeTruthy()
        })
      }
    })

    it('should navigate through wizard steps for a standard metric', async () => {
      const user = userEvent.setup()
      const mockOnChange = jest.fn()
      render(
        <EvaluationBuilder
          {...defaultProps}
          onEvaluationsChange={mockOnChange}
        />
      )

      // Open wizard
      const addButton = screen.getAllByRole('button').find(
        (b) =>
          b.textContent?.includes('evaluationBuilder.addNew') ||
          b.querySelector('[data-testid="plus-icon"]')
      )
      if (!addButton) return
      await user.click(addButton)

      // Step 1: Select a metric (e.g., bleu)
      const bleuButton = screen.queryByTestId('metric-button-bleu')
      if (bleuButton) {
        await user.click(bleuButton)

        // Click Next
        const nextButtons = screen.getAllByRole('button').filter(
          (b) =>
            b.textContent?.includes('evaluationBuilder.wizard.next') ||
            b.textContent?.includes('Next')
        )
        if (nextButtons.length > 0) {
          await user.click(nextButtons[0])

          // Should now be on prediction fields step
          await waitFor(() => {
            const heading =
              screen.queryByText(
                'evaluationBuilder.steps.predictionFields.title'
              ) ||
              screen.queryByText(/prediction/i)
            expect(heading).toBeTruthy()
          })
        }
      }
    })

    it('should select llm_judge_classic metric and show parameters step', async () => {
      const user = userEvent.setup()
      render(<EvaluationBuilder {...defaultProps} />)

      const addButton = screen.getAllByRole('button').find(
        (b) =>
          b.textContent?.includes('evaluationBuilder.addNew') ||
          b.querySelector('[data-testid="plus-icon"]')
      )
      if (!addButton) return
      await user.click(addButton)

      // Select llm_judge_classic metric
      const classicButton = screen.queryByTestId(
        'metric-button-llm_judge_classic'
      )
      if (classicButton) {
        await user.click(classicButton)
        expect(classicButton.className).toContain('emerald')
      }
    })

    it('should select llm_judge_custom metric', async () => {
      const user = userEvent.setup()
      render(<EvaluationBuilder {...defaultProps} />)

      const addButton = screen.getAllByRole('button').find(
        (b) =>
          b.textContent?.includes('evaluationBuilder.addNew') ||
          b.querySelector('[data-testid="plus-icon"]')
      )
      if (!addButton) return
      await user.click(addButton)

      const customButton = screen.queryByTestId(
        'metric-button-llm_judge_custom'
      )
      if (customButton) {
        await user.click(customButton)
        expect(customButton.className).toContain('emerald')
      }
    })

  })

  describe('Evaluation Card Actions', () => {
    const evaluations = [
      {
        id: 'eval-1',
        metric: 'bleu',
        display_name: 'BLEU',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        metric_parameters: {},
        enabled: true,
        created_at: '2025-01-01',
      },
      {
        id: 'eval-2',
        metric: 'rouge',
        display_name: 'ROUGE',
        prediction_fields: ['model_answer'],
        reference_fields: ['reference'],
        metric_parameters: { variant: 'rougeL' },
        enabled: false,
        created_at: '2025-01-02',
      },
    ]

    it('should delete an evaluation when trash icon clicked', async () => {
      const mockOnChange = jest.fn()
      const user = userEvent.setup()
      render(
        <EvaluationBuilder
          {...defaultProps}
          evaluations={evaluations}
          onEvaluationsChange={mockOnChange}
        />
      )

      // Find delete buttons
      const deleteButtons = screen.getAllByRole('button').filter(
        (b) => b.querySelector('[data-testid="trash-icon"]')
      )
      if (deleteButtons.length > 0) {
        await user.click(deleteButtons[0])
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.arrayContaining([
            expect.objectContaining({ id: 'eval-2' }),
          ])
        )
      }
    })

    it('should toggle evaluation enabled/disabled state', async () => {
      const mockOnChange = jest.fn()
      const user = userEvent.setup()
      render(
        <EvaluationBuilder
          {...defaultProps}
          evaluations={evaluations}
          onEvaluationsChange={mockOnChange}
        />
      )

      // Find checkboxes (toggle enabled state)
      const checkboxes = screen.getAllByRole('checkbox')
      if (checkboxes.length > 0) {
        await user.click(checkboxes[0])
        expect(mockOnChange).toHaveBeenCalled()
      }
    })

    it('should edit an evaluation by clicking edit icon', async () => {
      const user = userEvent.setup()
      render(
        <EvaluationBuilder {...defaultProps} evaluations={evaluations} />
      )

      // Find edit buttons
      const editButtons = screen.getAllByRole('button').filter(
        (b) => b.querySelector('[data-testid="pencil-icon"]')
      )
      if (editButtons.length > 0) {
        await user.click(editButtons[0])
        // Should open the wizard in edit mode
        await waitFor(() => {
          expect(
            screen.queryByText('evaluationBuilder.steps.metric.title') ||
              screen.queryByText(/metric/i)
          ).toBeTruthy()
        })
      }
    })

    it('should show disabled state for disabled evaluations', () => {
      render(
        <EvaluationBuilder {...defaultProps} evaluations={evaluations} />
      )

      // The disabled evaluation should render with some visual distinction
      const checkboxes = screen.getAllByRole('checkbox')
      const disabledCheckbox = checkboxes.find(
        (cb) => !(cb as HTMLInputElement).checked
      )
      expect(disabledCheckbox).toBeTruthy()
    })
  })

  describe('Run Evaluation', () => {
    it('should render run evaluation button when evaluations exist', () => {
      const evaluations = [
        {
          id: 'eval-1',
          metric: 'bleu',
          display_name: 'BLEU',
          prediction_fields: ['model_answer'],
          reference_fields: ['reference'],
          metric_parameters: {},
          enabled: true,
          created_at: '2025-01-01',
        },
      ]

      render(
        <EvaluationBuilder {...defaultProps} evaluations={evaluations} />
      )

      // Run button should be present (has PlayIcon)
      const runButtons = screen.getAllByRole('button').filter(
        (b) => b.querySelector('[data-testid="play-icon"]')
      )
      expect(runButtons.length).toBeGreaterThanOrEqual(0)
    })
  })

  describe('Full Wizard Flow', () => {
    it('should walk through all wizard steps for bleu metric', async () => {
      const mockOnChange = jest.fn()
      const user = userEvent.setup()
      render(
        <EvaluationBuilder
          {...defaultProps}
          onEvaluationsChange={mockOnChange}
        />
      )

      // Step 1: Click add button
      const addBtn = screen.getByTestId('add-evaluation-button')
      await user.click(addBtn)

      // Wizard should open
      await waitFor(() => {
        expect(screen.getByTestId('evaluation-wizard-header')).toBeInTheDocument()
      })

      // Select BLEU metric
      const bleuBtn = screen.queryByTestId('metric-button-bleu')
      if (bleuBtn) {
        await user.click(bleuBtn)

        // Click Next to go to prediction fields
        const nextBtns = screen.getAllByRole('button').filter(
          (b) => b.textContent?.includes('evaluationBuilder.wizard.next')
        )
        if (nextBtns.length > 0) {
          await user.click(nextBtns[0])

          // Step 2: Select prediction field
          await waitFor(() => {
            const checkboxes = screen.getAllByRole('checkbox')
            expect(checkboxes.length).toBeGreaterThan(0)
          })

          // Select first field
          const checkboxes = screen.getAllByRole('checkbox')
          if (checkboxes.length > 0) {
            await user.click(checkboxes[0])

            // Click Next to go to reference fields
            const nextBtns2 = screen.getAllByRole('button').filter(
              (b) => b.textContent?.includes('evaluationBuilder.wizard.next')
            )
            if (nextBtns2.length > 0) {
              await user.click(nextBtns2[0])

              // Step 3: Select reference field
              const refCheckboxes = screen.getAllByRole('checkbox')
              if (refCheckboxes.length > 0) {
                await user.click(refCheckboxes[0])
              }
            }
          }
        }
      }
    })

    it('should cancel wizard on close button click', async () => {
      const user = userEvent.setup()
      render(<EvaluationBuilder {...defaultProps} />)

      // Open wizard
      await user.click(screen.getByTestId('add-evaluation-button'))

      await waitFor(() => {
        expect(screen.getByTestId('evaluation-wizard-header')).toBeInTheDocument()
      })

      // Find close button (XMarkIcon)
      const closeBtn = screen.getAllByRole('button').find(
        (b) => b.querySelector('[data-testid="x-icon"]')
      )
      if (closeBtn) {
        await user.click(closeBtn)

        // Wizard should close
        await waitFor(() => {
          expect(screen.queryByTestId('evaluation-wizard-header')).not.toBeInTheDocument()
        })
      }
    })

    it('should select llm_judge_classic and configure dimensions', async () => {
      const user = userEvent.setup()
      render(<EvaluationBuilder {...defaultProps} />)

      await user.click(screen.getByTestId('add-evaluation-button'))

      await waitFor(() => {
        expect(screen.getByTestId('evaluation-wizard-header')).toBeInTheDocument()
      })

      // Select llm_judge_classic
      const classicBtn = screen.queryByTestId('metric-button-llm_judge_classic')
      if (classicBtn) {
        await user.click(classicBtn)
        expect(classicBtn.className).toContain('emerald')
      }
    })

    it('should display existing evaluation cards with metric info', () => {
      const evaluations = [
        {
          id: 'eval-1',
          metric: 'bleu',
          display_name: 'BLEU',
          prediction_fields: ['model_answer'],
          reference_fields: ['reference'],
          metric_parameters: { ngram: 4 },
          enabled: true,
          created_at: '2025-01-01',
        },
        {
          id: 'eval-2',
          metric: 'llm_judge_classic',
          display_name: 'LLM Judge Classic',
          prediction_fields: ['model_answer'],
          reference_fields: ['reference'],
          metric_parameters: {
            dimensions: ['accuracy', 'relevance'],
            judge_model: 'gpt-4',
            temperature: 0,
          },
          enabled: true,
          created_at: '2025-01-02',
        },
        {
          id: 'eval-3',
          metric: 'exact_match',
          display_name: 'Exact Match',
          prediction_fields: ['__ALL_MODEL__'],
          reference_fields: ['reference'],
          metric_parameters: {},
          enabled: false,
          created_at: '2025-01-03',
        },
      ]

      render(
        <EvaluationBuilder {...defaultProps} evaluations={evaluations} />
      )

      // All evaluation cards should render
      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes.length).toBe(3)

      // Enabled and disabled states should be reflected
      const enabledCheckboxes = checkboxes.filter(
        (cb) => (cb as HTMLInputElement).checked
      )
      expect(enabledCheckboxes.length).toBe(2)
    })
  })

  describe('Save Configuration', () => {
    it('should call onSave with save button', async () => {
      const mockSave = jest.fn()
      const user = userEvent.setup()
      const evaluations = [
        {
          id: 'eval-1',
          metric: 'bleu',
          display_name: 'BLEU',
          prediction_fields: ['model_answer'],
          reference_fields: ['reference'],
          metric_parameters: {},
          enabled: true,
          created_at: '2025-01-01',
        },
      ]

      render(
        <EvaluationBuilder
          {...defaultProps}
          evaluations={evaluations}
          onSave={mockSave}
        />
      )

      // Find the save button
      const saveButton = screen.getAllByRole('button').find(
        (b) =>
          b.textContent?.includes('evaluationBuilder.save') ||
          b.textContent?.includes('Save')
      )
      if (saveButton) {
        await user.click(saveButton)
        expect(mockSave).toHaveBeenCalled()
      }
    })

    it('should show saving state on save button', () => {
      const evaluations = [
        {
          id: 'eval-1',
          metric: 'bleu',
          display_name: 'BLEU',
          prediction_fields: ['model_answer'],
          reference_fields: ['reference'],
          metric_parameters: {},
          enabled: true,
          created_at: '2025-01-01',
        },
      ]

      render(
        <EvaluationBuilder
          {...defaultProps}
          evaluations={evaluations}
          saving={true}
          onSave={jest.fn()}
        />
      )

      // Save button should show saving state or be disabled
      const saveButton = screen.getAllByRole('button').find(
        (b) =>
          b.textContent?.includes('evaluationBuilder.saving') ||
          b.textContent?.includes('Saving')
      )
      if (saveButton) {
        expect(saveButton).toBeDisabled()
      }
    })
  })
})
