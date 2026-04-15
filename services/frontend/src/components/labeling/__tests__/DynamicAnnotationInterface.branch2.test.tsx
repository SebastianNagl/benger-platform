/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for DynamicAnnotationInterface.
 * Targets uncovered conditional branches:
 * - initialValues: textarea with text as string (not array)
 * - requireConfirmBeforeSubmit blocking submit and skip
 * - Keyboard shortcuts blocked by requireConfirmBeforeSubmit
 * - enableAutoSave=false path
 * - handleSubmit building from componentValues when no annotations
 * - AutoSaveIndicator rendering when enableAutoSave=true
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DynamicAnnotationInterface } from '../DynamicAnnotationInterface'

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'annotation.interface.configError': 'Configuration Error',
        'annotation.interface.missingFields': 'Missing required fields: {fields}',
        'annotation.interface.atLeastOne': 'At least one annotation is required',
        'annotation.interface.fieldRequired': 'Field "{fieldName}" is required',
        'annotation.interface.submissionError': 'Error submitting annotations',
        'annotation.interface.taskData': 'Task Data',
        'annotation.interface.skip': 'Skip',
        'annotation.interface.skipShortcut': '(Ctrl+ESC)',
        'annotation.interface.submit': 'Submit',
        'annotation.interface.submitShortcut': 'Ctrl+Enter',
        'annotation.interface.tip': 'Use keyboard shortcuts for faster annotation',
        'annotation.interface.confirmDone': 'I confirm that I have read the annotation instructions and am ready to submit',
      }
      let value = translations[key] || key
      if (params) {
        value = value.replace(/\{(\w+)\}/g, (match: string, variableName: string) => {
          return params[variableName] !== undefined ? String(params[variableName]) : match
        })
      }
      return value
    },
    locale: 'en',
  }),
}))

// Mock the label config parser
jest.mock('@/lib/labelConfig/parser', () => ({
  parseLabelConfig: jest.fn(),
  validateParsedConfig: jest.fn(),
  extractDataFields: jest.fn(),
  extractRequiredDataFields: jest.fn(),
}))

// Mock the data binding utilities
jest.mock('@/lib/labelConfig/dataBinding', () => ({
  resolvePropsDataBindings: jest.fn(),
  validateTaskDataFields: jest.fn(),
  buildAnnotationResult: jest.fn(),
}))

// Mock shared components
jest.mock('@/components/shared/Alert', () => ({
  Alert: function MockAlert({ children }: any) {
    return <div data-testid="alert">{children}</div>
  },
}))

jest.mock('@/components/shared/Skeleton', () => ({
  Skeleton: function MockSkeleton(props: any) {
    return <div data-testid="skeleton" {...props} />
  },
}))

jest.mock('@/components/shared/AutoSaveIndicator', () => ({
  AutoSaveIndicator: ({ isSaving, lastSaved, error }: any) => (
    <div data-testid="auto-save-indicator">
      {isSaving && 'saving'}
      {lastSaved && 'saved'}
      {error && 'error'}
    </div>
  ),
}))

// Mock useAutoSave
jest.mock('@/hooks/useAutoSave', () => ({
  useAutoSave: () => ({
    isSaving: false,
    lastSaved: null,
    error: null,
    loadDraft: jest.fn().mockReturnValue(null),
    clearDraft: jest.fn(),
    saveNow: jest.fn().mockResolvedValue(undefined),
  }),
}))

// Store mock components
;(global as any).__mockTextAreaComponent = jest.fn(
  ({ hideSubmitButton, config, value, onChange, onAnnotation }: any) => {
    return (
      <div data-testid="mock-textarea">
        <textarea
          data-testid="textarea"
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
        />
        {!hideSubmitButton && (
          <button
            data-testid="component-submit-button"
            onClick={() =>
              onAnnotation({ from_name: config?.name || config?.props?.name, to_name: 'text', type: 'textarea', value: value })
            }
          >
            Submit
          </button>
        )}
      </div>
    )
  }
)

;(global as any).__mockViewComponent = jest.fn(({ children }: any) => (
  <div data-testid="mock-view">{children}</div>
))

jest.mock('@/lib/labelConfig/registry', () => ({
  getComponent: jest.fn((type: string) => {
    const components: Record<string, any> = {
      TextArea: {
        component: (global as any).__mockTextAreaComponent,
        category: 'control',
      },
      View: {
        component: (global as any).__mockViewComponent,
        category: 'visual',
      },
    }
    return components[type] || null
  }),
  createComponentInstance: jest.fn(),
}))

// Import mocked modules
import {
  resolvePropsDataBindings,
  validateTaskDataFields,
} from '@/lib/labelConfig/dataBinding'
import {
  extractRequiredDataFields,
  parseLabelConfig,
  validateParsedConfig,
} from '@/lib/labelConfig/parser'

const mockParseLabelConfig = parseLabelConfig as jest.MockedFunction<typeof parseLabelConfig>
const mockValidateParsedConfig = validateParsedConfig as jest.MockedFunction<typeof validateParsedConfig>
const mockExtractRequiredDataFields = extractRequiredDataFields as jest.MockedFunction<typeof extractRequiredDataFields>
const mockResolvePropsDataBindings = resolvePropsDataBindings as jest.MockedFunction<typeof resolvePropsDataBindings>
const mockValidateTaskDataFields = validateTaskDataFields as jest.MockedFunction<typeof validateTaskDataFields>

const textareaParsedConfig = {
  type: 'View',
  name: 'root',
  props: {},
  children: [
    {
      type: 'TextArea',
      name: 'answer',
      props: { name: 'answer', toName: 'text', placeholder: 'Type...' },
      children: [],
    },
  ],
}

describe('DynamicAnnotationInterface - branch coverage', () => {
  const defaultProps = {
    labelConfig: '<View><TextArea name="answer"/></View>',
    taskData: { text: 'Test' },
    onSubmit: jest.fn(),
    onSkip: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    ;(global as any).__mockTextAreaComponent.mockClear()
    ;(global as any).__mockViewComponent.mockClear()

    mockParseLabelConfig.mockReturnValue(textareaParsedConfig)
    mockValidateParsedConfig.mockReturnValue({ valid: true, errors: [] })
    mockExtractRequiredDataFields.mockReturnValue([])
    mockResolvePropsDataBindings.mockImplementation((props) => props)
    mockValidateTaskDataFields.mockReturnValue({ valid: true, missingFields: [] })
  })

  describe('requireConfirmBeforeSubmit', () => {
    it('shows confirmation checkbox when requireConfirmBeforeSubmit=true', () => {
      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          requireConfirmBeforeSubmit={true}
        />
      )

      expect(
        screen.getByText(/I confirm that I have read the annotation instructions/i)
      ).toBeInTheDocument()
    })

    it('disables submit button until confirmation checkbox is checked', async () => {
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          requireConfirmBeforeSubmit={true}
        />
      )

      // Type something first to have data
      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'test')

      // Submit button should be disabled (not confirmed)
      const submitButtons = screen.getAllByRole('button', { name: /submit/i })
      const mainSubmit = submitButtons.find((b) => b.classList.contains('bg-emerald-600'))
      expect(mainSubmit).toBeDisabled()

      // Check the confirmation checkbox
      const checkbox = screen.getByRole('checkbox')
      await user.click(checkbox)

      // Now submit should be enabled
      expect(mainSubmit).not.toBeDisabled()
    })

    it('disables skip button until confirmation is checked', async () => {
      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          requireConfirmBeforeSubmit={true}
        />
      )

      const skipButton = screen.getByRole('button', { name: /skip/i })
      expect(skipButton).toBeDisabled()
    })

    it('blocks Ctrl+Enter submit when confirmation not checked', () => {
      const mockOnSubmit = jest.fn()

      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          onSubmit={mockOnSubmit}
          requireConfirmBeforeSubmit={true}
        />
      )

      fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })

      // Should NOT submit because confirmation not checked
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('blocks Ctrl+Escape skip when confirmation not checked', () => {
      const mockOnSkip = jest.fn()

      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          onSkip={mockOnSkip}
          requireConfirmBeforeSubmit={true}
        />
      )

      fireEvent.keyDown(window, { key: 'Escape', ctrlKey: true })

      // Should NOT skip because confirmation not checked
      expect(mockOnSkip).not.toHaveBeenCalled()
    })
  })

  describe('initialValues type branches', () => {
    it('handles textarea initial value with text as string (not array)', () => {
      const initialValues = [
        {
          from_name: 'answer',
          to_name: 'text',
          type: 'textarea' as const,
          value: { text: 'Single string value' },
        },
      ]

      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          initialValues={initialValues}
        />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveValue('Single string value')
    })

  })

  describe('enableAutoSave=false', () => {
    it('does not show AutoSaveIndicator when enableAutoSave is false', () => {
      render(
        <DynamicAnnotationInterface {...defaultProps} enableAutoSave={false} />
      )

      expect(screen.queryByTestId('auto-save-indicator')).not.toBeInTheDocument()
    })

    it('shows AutoSaveIndicator when enableAutoSave is true (default)', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getByTestId('auto-save-indicator')).toBeInTheDocument()
    })
  })

  describe('submit building from componentValues', () => {
    it('builds results from componentValues when no formal annotations exist', async () => {
      const mockOnSubmit = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      // Type in the textarea to create componentValues
      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'My answer')

      // Submit - should build from componentValues since no onAnnotation was called
      const submitButtons = screen.getAllByRole('button', { name: /submit/i })
      const mainSubmit = submitButtons.find((b) => b.classList.contains('bg-emerald-600'))
      fireEvent.click(mainSubmit!)

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.arrayContaining([
            expect.objectContaining({
              from_name: 'answer',
              type: 'textarea',
            }),
          ])
        )
      })
    })
  })

  describe('Label and Choice child types silently skipped', () => {
    it('silently skips Label and Choice types without console.warn', () => {
      const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation()

      const configWithLabelAndChoice = {
        type: 'View',
        name: 'root',
        props: {},
        children: [
          { type: 'Label', name: 'label-1', props: {}, children: [] },
          { type: 'Choice', name: 'choice-1', props: {}, children: [] },
          { type: 'UnknownCustom', name: 'custom-1', props: {}, children: [] },
        ],
      }

      mockParseLabelConfig.mockReturnValue(configWithLabelAndChoice)
      render(<DynamicAnnotationInterface {...defaultProps} />)

      // Label and Choice should NOT trigger console.warn
      // But UnknownCustom should
      const warnCalls = consoleWarnSpy.mock.calls.filter(
        (call) => typeof call[0] === 'string' && call[0].includes('Unknown component type')
      )
      expect(warnCalls.length).toBe(1)
      expect(warnCalls[0][0]).toContain('UnknownCustom')

      consoleWarnSpy.mockRestore()
    })
  })
})
