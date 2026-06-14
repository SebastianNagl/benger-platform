/**
 * Behavioral tests for the StepPrompts wizard step.
 *
 * Covers uncovered branches: selecting a preset template (which seeds the
 * system + instruction prompts), selecting the "custom" template (which does
 * NOT overwrite the prompts), typing in either textarea, inserting a variable
 * via the variable chips (cursor-aware path), and the no-variables Alert.
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { StepPrompts } from '../StepPrompts'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) =>
      typeof fallback === 'string' ? fallback : key,
    locale: 'en',
  }),
}))

interface RenderArgs {
  promptTemplate?: string
  systemPrompt?: string
  instructionPrompt?: string
  availableVariables?: string[]
}

function renderStep(args: RenderArgs = {}) {
  const onPromptTemplateChange = jest.fn()
  const onSystemPromptChange = jest.fn()
  const onInstructionPromptChange = jest.fn()
  const utils = render(
    <StepPrompts
      promptTemplate={args.promptTemplate ?? 'custom'}
      systemPrompt={args.systemPrompt ?? ''}
      instructionPrompt={args.instructionPrompt ?? ''}
      availableVariables={args.availableVariables ?? []}
      onPromptTemplateChange={onPromptTemplateChange}
      onSystemPromptChange={onSystemPromptChange}
      onInstructionPromptChange={onInstructionPromptChange}
    />
  )
  return {
    onPromptTemplateChange,
    onSystemPromptChange,
    onInstructionPromptChange,
    ...utils,
  }
}

describe('StepPrompts', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('template selection', () => {
    it('seeds system + instruction prompts when a preset template is chosen', () => {
      const {
        onPromptTemplateChange,
        onSystemPromptChange,
        onInstructionPromptChange,
      } = renderStep({ promptTemplate: 'custom' })

      fireEvent.click(
        screen.getByTestId('wizard-prompt-template-question-answering')
      )

      expect(onPromptTemplateChange).toHaveBeenCalledWith('question-answering')
      expect(onSystemPromptChange).toHaveBeenCalledWith(
        expect.stringContaining('expert assistant')
      )
      expect(onInstructionPromptChange).toHaveBeenCalledWith(
        expect.stringContaining('$context')
      )
    })

    it('selecting the custom template does not overwrite the prompts', () => {
      const {
        onPromptTemplateChange,
        onSystemPromptChange,
        onInstructionPromptChange,
      } = renderStep({ promptTemplate: 'legal-analysis' })

      fireEvent.click(screen.getByTestId('wizard-prompt-template-custom'))

      expect(onPromptTemplateChange).toHaveBeenCalledWith('custom')
      expect(onSystemPromptChange).not.toHaveBeenCalled()
      expect(onInstructionPromptChange).not.toHaveBeenCalled()
    })

    it('seeds German legal prompts for the legal-analysis template', () => {
      const { onSystemPromptChange } = renderStep({ promptTemplate: 'custom' })
      fireEvent.click(screen.getByTestId('wizard-prompt-template-legal-analysis'))
      expect(onSystemPromptChange).toHaveBeenCalledWith(
        expect.stringContaining('deutsches Recht')
      )
    })
  })

  describe('prompt text editing', () => {
    it('emits system prompt changes', () => {
      const { onSystemPromptChange } = renderStep()
      fireEvent.change(screen.getByTestId('wizard-system-prompt'), {
        target: { value: 'You are helpful' },
      })
      expect(onSystemPromptChange).toHaveBeenCalledWith('You are helpful')
    })

    it('emits instruction prompt changes', () => {
      const { onInstructionPromptChange } = renderStep()
      fireEvent.change(screen.getByTestId('wizard-instruction-prompt'), {
        target: { value: 'Do the thing' },
      })
      expect(onInstructionPromptChange).toHaveBeenCalledWith('Do the thing')
    })
  })

  describe('variable insertion', () => {
    it('shows variable chips only when variables are available', () => {
      const { rerender } = renderStep({ availableVariables: [] })
      expect(screen.queryByText('$question')).not.toBeInTheDocument()
      // The no-variables informational note should be visible
      expect(
        screen.getByText('projects.creation.wizard.step6.noVariablesNote')
      ).toBeInTheDocument()

      rerender(
        <StepPrompts
          promptTemplate="custom"
          systemPrompt=""
          instructionPrompt=""
          availableVariables={['question']}
          onPromptTemplateChange={jest.fn()}
          onSystemPromptChange={jest.fn()}
          onInstructionPromptChange={jest.fn()}
        />
      )
      // Two chips render: one for system prompt, one for instruction prompt
      expect(screen.getAllByText('$question').length).toBeGreaterThanOrEqual(2)
    })

    it('inserts a variable into the system prompt at the cursor position', () => {
      const { onSystemPromptChange } = renderStep({
        systemPrompt: 'Hello world',
        availableVariables: ['context'],
      })

      const textarea = screen.getByTestId(
        'wizard-system-prompt'
      ) as HTMLTextAreaElement
      // Place the cursor between "Hello" and " world"
      textarea.setSelectionRange(5, 5)

      // The first $context chip belongs to the system-prompt block
      const chips = screen.getAllByText('$context')
      fireEvent.click(chips[0])

      expect(onSystemPromptChange).toHaveBeenCalledWith('Hello$context world')
    })

    it('inserts a variable into the instruction prompt', () => {
      const { onInstructionPromptChange } = renderStep({
        instructionPrompt: 'Answer:',
        availableVariables: ['answer'],
      })

      const textarea = screen.getByTestId(
        'wizard-instruction-prompt'
      ) as HTMLTextAreaElement
      textarea.setSelectionRange(
        textarea.value.length,
        textarea.value.length
      )

      // chips[1] is the instruction-prompt copy of the variable chip
      const chips = screen.getAllByText('$answer')
      fireEvent.click(chips[1])

      expect(onInstructionPromptChange).toHaveBeenCalledWith('Answer:$answer')
    })
  })
})
