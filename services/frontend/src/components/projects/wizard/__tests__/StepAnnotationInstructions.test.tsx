/**
 * Behavioral tests for the StepAnnotationInstructions wizard step.
 *
 * Covers uncovered branches: editing the base instructions, expanding the
 * conditional-variants panel, adding the first variant (weight 100) and a
 * second variant (weight 0), editing variant id / weight / content /
 * ai_allowed, removing a variant, the weight-sum validation error, and the
 * three display-setting checkboxes.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { StepAnnotationInstructions } from '../StepAnnotationInstructions'
import { ConditionalInstruction } from '../types'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      if (params && typeof params === 'object') {
        return `${key} ${JSON.stringify(params)}`
      }
      return key
    },
    locale: 'en',
  }),
}))

interface RenderArgs {
  instructions?: string
  conditionalInstructions?: ConditionalInstruction[]
  showInstruction?: boolean
  instructionsAlwaysVisible?: boolean
  showSkipButton?: boolean
}

function renderStep(args: RenderArgs = {}) {
  const onInstructionsChange = jest.fn()
  const onConditionalInstructionsChange = jest.fn()
  const onShowInstructionChange = jest.fn()
  const onInstructionsAlwaysVisibleChange = jest.fn()
  const onShowSkipButtonChange = jest.fn()

  const utils = render(
    <StepAnnotationInstructions
      instructions={args.instructions ?? ''}
      conditionalInstructions={args.conditionalInstructions ?? []}
      showInstruction={args.showInstruction ?? true}
      instructionsAlwaysVisible={args.instructionsAlwaysVisible ?? false}
      showSkipButton={args.showSkipButton ?? true}
      onInstructionsChange={onInstructionsChange}
      onConditionalInstructionsChange={onConditionalInstructionsChange}
      onShowInstructionChange={onShowInstructionChange}
      onInstructionsAlwaysVisibleChange={onInstructionsAlwaysVisibleChange}
      onShowSkipButtonChange={onShowSkipButtonChange}
    />
  )
  return {
    onInstructionsChange,
    onConditionalInstructionsChange,
    onShowInstructionChange,
    onInstructionsAlwaysVisibleChange,
    onShowSkipButtonChange,
    ...utils,
  }
}

const oneVariant: ConditionalInstruction[] = [
  { id: 'variant_1', content: 'Do A', weight: 100, ai_allowed: false },
]

describe('StepAnnotationInstructions', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('emits base instruction changes', () => {
    const { onInstructionsChange } = renderStep()
    fireEvent.change(screen.getByTestId('wizard-instructions-textarea'), {
      target: { value: 'Read carefully' },
    })
    expect(onInstructionsChange).toHaveBeenCalledWith('Read carefully')
  })

  describe('variants panel', () => {
    it('is collapsed by default when there are no variants', () => {
      renderStep({ conditionalInstructions: [] })
      // The add-variant button lives inside the collapsed panel
      expect(screen.queryByTestId('wizard-add-variant')).not.toBeInTheDocument()
    })

    it('starts expanded when variants already exist', () => {
      renderStep({ conditionalInstructions: oneVariant })
      expect(screen.getByTestId('wizard-add-variant')).toBeInTheDocument()
      expect(screen.getByTestId('wizard-variant-0')).toBeInTheDocument()
    })

    it('expands the panel when the toggle is clicked', () => {
      renderStep({ conditionalInstructions: [] })
      fireEvent.click(screen.getByTestId('wizard-variants-toggle'))
      expect(screen.getByTestId('wizard-add-variant')).toBeInTheDocument()
    })

    it('adds the first variant with weight 100', () => {
      const { onConditionalInstructionsChange } = renderStep({
        conditionalInstructions: [],
      })
      fireEvent.click(screen.getByTestId('wizard-variants-toggle'))
      fireEvent.click(screen.getByTestId('wizard-add-variant'))
      expect(onConditionalInstructionsChange).toHaveBeenCalledWith([
        expect.objectContaining({
          id: 'variant_1',
          content: '',
          weight: 100,
          ai_allowed: false,
        }),
      ])
    })

    it('adds a subsequent variant with weight 0', () => {
      const { onConditionalInstructionsChange } = renderStep({
        conditionalInstructions: oneVariant,
      })
      fireEvent.click(screen.getByTestId('wizard-add-variant'))
      expect(onConditionalInstructionsChange).toHaveBeenCalledWith([
        ...oneVariant,
        expect.objectContaining({ id: 'variant_2', weight: 0 }),
      ])
    })

    it('removes a variant by index', () => {
      const twoVariants: ConditionalInstruction[] = [
        { id: 'variant_1', content: 'A', weight: 60, ai_allowed: false },
        { id: 'variant_2', content: 'B', weight: 40, ai_allowed: true },
      ]
      const { onConditionalInstructionsChange } = renderStep({
        conditionalInstructions: twoVariants,
      })
      fireEvent.click(screen.getByTestId('wizard-variant-remove-0'))
      expect(onConditionalInstructionsChange).toHaveBeenCalledWith([
        twoVariants[1],
      ])
    })
  })

  describe('variant field edits', () => {
    it('updates the variant id', () => {
      const { onConditionalInstructionsChange } = renderStep({
        conditionalInstructions: oneVariant,
      })
      const idInput = screen.getByDisplayValue('variant_1')
      fireEvent.change(idInput, { target: { value: 'variant_a' } })
      expect(onConditionalInstructionsChange).toHaveBeenCalledWith([
        expect.objectContaining({ id: 'variant_a' }),
      ])
    })

    it('updates the variant weight as a number', () => {
      const { onConditionalInstructionsChange } = renderStep({
        conditionalInstructions: oneVariant,
      })
      const weightInput = screen.getByDisplayValue('100')
      fireEvent.change(weightInput, { target: { value: '70' } })
      expect(onConditionalInstructionsChange).toHaveBeenCalledWith([
        expect.objectContaining({ weight: 70 }),
      ])
    })

    it('updates the variant content', () => {
      const { onConditionalInstructionsChange } = renderStep({
        conditionalInstructions: oneVariant,
      })
      const contentInput = screen.getByDisplayValue('Do A')
      fireEvent.change(contentInput, { target: { value: 'Do B' } })
      expect(onConditionalInstructionsChange).toHaveBeenCalledWith([
        expect.objectContaining({ content: 'Do B' }),
      ])
    })

    it('toggles ai_allowed for a variant', () => {
      const { onConditionalInstructionsChange } = renderStep({
        conditionalInstructions: oneVariant,
      })
      const variant = screen.getByTestId('wizard-variant-0')
      const aiCheckbox = variant.querySelector(
        'input[type="checkbox"]'
      ) as HTMLInputElement
      fireEvent.click(aiCheckbox)
      expect(onConditionalInstructionsChange).toHaveBeenCalledWith([
        expect.objectContaining({ ai_allowed: true }),
      ])
    })
  })

  describe('weight validation', () => {
    it('shows the weight error when the variant weights do not sum to 100', () => {
      renderStep({
        conditionalInstructions: [
          { id: 'variant_1', content: 'A', weight: 60, ai_allowed: false },
          { id: 'variant_2', content: 'B', weight: 30, ai_allowed: false },
        ],
      })
      // weightError translation key gets interpolated with the sum (90)
      expect(
        screen.getByText(/projects\.creation\.wizard\.step4\.weightError/)
      ).toBeInTheDocument()
    })

    it('does not show the weight error when weights sum to 100', () => {
      renderStep({
        conditionalInstructions: [
          { id: 'variant_1', content: 'A', weight: 60, ai_allowed: false },
          { id: 'variant_2', content: 'B', weight: 40, ai_allowed: false },
        ],
      })
      expect(
        screen.queryByText(/projects\.creation\.wizard\.step4\.weightError/)
      ).not.toBeInTheDocument()
    })
  })

  describe('display settings', () => {
    it('toggles show-instruction off', () => {
      const { onShowInstructionChange } = renderStep({ showInstruction: true })
      const label = screen.getByText(
        'projects.creation.wizard.step4.showInstructions'
      )
      const row = label.closest('.flex')!
      const checkbox = row.querySelector(
        'input[type="checkbox"]'
      ) as HTMLInputElement
      expect(checkbox).toBeChecked()
      fireEvent.click(checkbox)
      expect(onShowInstructionChange).toHaveBeenCalledWith(false)
    })

    it('toggles always-visible on', () => {
      const { onInstructionsAlwaysVisibleChange } = renderStep({
        instructionsAlwaysVisible: false,
      })
      const label = screen.getByText(
        'projects.creation.wizard.step4.alwaysShowInstructions'
      )
      const row = label.closest('.flex')!
      const checkbox = row.querySelector(
        'input[type="checkbox"]'
      ) as HTMLInputElement
      fireEvent.click(checkbox)
      expect(onInstructionsAlwaysVisibleChange).toHaveBeenCalledWith(true)
    })

    it('toggles show-skip-button off', () => {
      const { onShowSkipButtonChange } = renderStep({ showSkipButton: true })
      const label = screen.getByText(
        'projects.creation.wizard.step4.showSkipButton'
      )
      const row = label.closest('.flex')!
      const checkbox = row.querySelector(
        'input[type="checkbox"]'
      ) as HTMLInputElement
      fireEvent.click(checkbox)
      expect(onShowSkipButtonChange).toHaveBeenCalledWith(false)
    })
  })
})
