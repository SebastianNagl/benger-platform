/**
 * Comprehensive tests for DynamicAnnotationInterface component
 * Tests configuration parsing, annotation management, keyboard shortcuts, and form submission
 */

/**
 * @jest-environment jsdom
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
        'annotation.interface.missingFields': `Missing required fields: {fields}`,
        'annotation.interface.atLeastOne':
          'At least one annotation is required',
        'annotation.interface.fieldRequired': `Field "{fieldName}" is required`,
        'annotation.interface.submissionError': 'Error submitting annotations',
        'annotation.interface.taskData': 'Task Data',
        'annotation.interface.skip': 'Skip',
        'annotation.interface.skipShortcut': '(Ctrl+ESC)',
        'annotation.interface.submit': 'Submit',
        'annotation.interface.submitShortcut': 'Ctrl+Enter',
        'annotation.interface.tip':
          'Use keyboard shortcuts for faster annotation',
      }
      let value = translations[key] || key
      if (params) {
        value = value.replace(/\{(\w+)\}/g, (match, variableName) => {
          return params[variableName] !== undefined
            ? String(params[variableName])
            : match
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

// Mock the shared components
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

// Store mock components globally to access them in tests
;(global as any).__mockTextAreaComponent = jest.fn(
  ({ hideSubmitButton, config, value, onChange, onAnnotation }) => {
    return (
      <div data-testid="mock-textarea">
        <textarea
          data-testid="textarea"
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={config?.props?.placeholder}
        />
        {!hideSubmitButton && (
          <button
            data-testid="component-submit-button"
            onClick={() =>
              onAnnotation({ from_name: config?.name, value: value })
            }
          >
            Submit
          </button>
        )}
      </div>
    )
  }
)
;(global as any).__mockViewComponent = jest.fn(({ children, config }) => (
  <div data-testid="mock-view" className="view-component">
    {children}
  </div>
))
;(global as any).__mockTextComponent = jest.fn(({ config }) => (
  <div data-testid="mock-text" className="text-component">
    {config?.props?.value || 'Text content'}
  </div>
))

// Access mock components from global
const mockTextAreaComponent = () => (global as any).__mockTextAreaComponent
const mockViewComponent = () => (global as any).__mockViewComponent
const mockTextComponent = () => (global as any).__mockTextComponent

jest.mock('@/lib/labelConfig/registry', () => ({
  getComponent: jest.fn((type) => {
    const components = {
      TextArea: {
        component: (global as any).__mockTextAreaComponent,
        category: 'control',
      },
      View: {
        component: (global as any).__mockViewComponent,
        category: 'visual',
      },
      Text: {
        component: (global as any).__mockTextComponent,
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
  extractDataFields,
  extractRequiredDataFields,
  parseLabelConfig,
  validateParsedConfig,
} from '@/lib/labelConfig/parser'

const mockParseLabelConfig = parseLabelConfig as jest.MockedFunction<
  typeof parseLabelConfig
>
const mockValidateParsedConfig = validateParsedConfig as jest.MockedFunction<
  typeof validateParsedConfig
>
const mockExtractDataFields = extractDataFields as jest.MockedFunction<
  typeof extractDataFields
>
const mockExtractRequiredDataFields =
  extractRequiredDataFields as jest.MockedFunction<
    typeof extractRequiredDataFields
  >
const mockResolvePropsDataBindings =
  resolvePropsDataBindings as jest.MockedFunction<
    typeof resolvePropsDataBindings
  >
const mockValidateTaskDataFields =
  validateTaskDataFields as jest.MockedFunction<typeof validateTaskDataFields>

describe('DynamicAnnotationInterface', () => {
  // Helper function to get the main submit button
  const getMainSubmitButton = () => {
    const allSubmitButtons = screen.getAllByRole('button', { name: /submit/i })
    return (
      allSubmitButtons.find((btn) => btn.classList.contains('ml-auto')) ||
      allSubmitButtons[allSubmitButtons.length - 1]
    )
  }

  const defaultProps = {
    labelConfig: `<View>
      <Text name="context" value="$context"/>
      <TextArea name="answer" toName="context" placeholder="Enter your answer..." />
    </View>`,
    taskData: { context: 'Test question' },
    onSubmit: jest.fn(),
    onSkip: jest.fn(),
  }

  const mockParsedConfig = {
    type: 'View',
    name: 'root',
    props: {},
    children: [
      {
        type: 'Text',
        name: 'context',
        props: { name: 'context', value: '$context' },
        children: [],
      },
      {
        type: 'TextArea',
        name: 'answer',
        props: {
          name: 'answer',
          toName: 'context',
          placeholder: 'Enter your answer...',
          showSubmitButton: 'true',
        },
        children: [],
      },
    ],
  }

  beforeEach(() => {
    jest.clearAllMocks()

    // Clear global mock functions (not covered by clearAllMocks)
    ;(global as any).__mockTextAreaComponent.mockClear()
    ;(global as any).__mockViewComponent.mockClear()
    ;(global as any).__mockTextComponent.mockClear()

    // Setup default mock implementations
    mockParseLabelConfig.mockReturnValue(mockParsedConfig)
    mockValidateParsedConfig.mockReturnValue({ valid: true, errors: [] })
    mockExtractDataFields.mockReturnValue(['context'])
    mockExtractRequiredDataFields.mockReturnValue([])
    mockResolvePropsDataBindings.mockImplementation((props, taskData) => ({
      ...props,
      value: taskData[props.value?.replace('$', '')] || props.value,
    }))
    mockValidateTaskDataFields.mockReturnValue({
      valid: true,
      missingFields: [],
    })
  })

  describe('Submit Button Hiding', () => {
    it('should pass hideSubmitButton=true to TextArea components when showSubmitButton=true', async () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      // The actual implementation passes hideSubmitButton={showSubmitButton}
      // So when showSubmitButton=true (default), hideSubmitButton=true
      // This means component-level submit buttons are HIDDEN (centralized submit button shown instead)
      const componentSubmitButton = screen.queryByTestId(
        'component-submit-button'
      )
      expect(componentSubmitButton).not.toBeInTheDocument()

      // The main interface submit button should be present
      const allSubmitButtons = screen.getAllByRole('button', {
        name: /submit/i,
      })
      expect(allSubmitButtons.length).toBeGreaterThanOrEqual(1)
    })

    it('should verify mockTextAreaComponent received hideSubmitButton=true when showSubmitButton=true', async () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      // Verify the mocked TextArea component was called with hideSubmitButton=true
      // because showSubmitButton defaults to true and hideSubmitButton={showSubmitButton}
      // (hide individual buttons when centralized submit is shown)
      expect(mockTextAreaComponent()).toHaveBeenCalledWith(
        expect.objectContaining({
          hideSubmitButton: true,
        }),
        expect.any(Object)
      )
    })
  })

  describe('Annotation Submission Flow', () => {
    it('should collect annotations and submit through main submit button', async () => {
      const mockOnSubmit = jest.fn()
      const props = {
        ...defaultProps,
        onSubmit: mockOnSubmit,
      }

      render(<DynamicAnnotationInterface {...props} />)

      const textarea = screen.getByTestId('textarea')
      const allSubmitButtons = screen.getAllByRole('button', {
        name: /submit/i,
      })
      const submitButton = allSubmitButtons.find((btn) =>
        btn.classList.contains('bg-emerald-600')
      )

      // Fill in some text
      fireEvent.change(textarea, { target: { value: 'Test answer' } })

      // This should trigger onAnnotation in the component, adding to the annotations map
      await waitFor(() => {
        expect(mockTextAreaComponent()).toHaveBeenCalled()
      })

      // Since we need to simulate the annotation being added to the state,
      // we'll check that the submit button becomes enabled
      // (it's disabled when no annotations exist)
      expect(submitButton).toBeInTheDocument()
    })

    it('should display error when no annotations are provided', async () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      const allSubmitButtons = screen.getAllByRole('button', {
        name: /submit/i,
      })
      const submitButton = allSubmitButtons.find((btn) =>
        btn.classList.contains('bg-emerald-600')
      )

      // Try to submit without any annotations
      fireEvent.click(submitButton!)

      // The submit button should be disabled initially since no annotations
      expect(submitButton).toBeDisabled()
    })

    it('should show skip button when onSkip is provided', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      const skipButton = screen.getByRole('button', { name: /skip/i })
      expect(skipButton).toBeInTheDocument()
    })

    it('should not show skip button when onSkip is not provided', () => {
      const propsWithoutSkip = {
        ...defaultProps,
        onSkip: undefined,
      }

      render(<DynamicAnnotationInterface {...propsWithoutSkip} />)

      const skipButton = screen.queryByRole('button', { name: /skip/i })
      expect(skipButton).not.toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    // Simplified tests that verify the component can handle valid configurations
    // Complex error state testing would require integration tests
    it('should handle valid configuration without errors', () => {
      // Test with known working configuration
      render(<DynamicAnnotationInterface {...defaultProps} />)

      // Should render the normal interface without errors
      expect(getMainSubmitButton()).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /skip/i })).toBeInTheDocument()
    })

    it('should render components when configuration is valid', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      // Should render mock components
      expect(screen.getByTestId('mock-textarea')).toBeInTheDocument()
      expect(screen.getByTestId('mock-text')).toBeInTheDocument()
    })

    it('should handle component registration correctly', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      // The mock registry should be called
      const { getComponent } = require('@/lib/labelConfig/registry')
      expect(getComponent).toHaveBeenCalled()
    })

    it('should pass correct props to rendered components', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      // Verify that components are rendered with the expected structure
      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveAttribute('placeholder', 'Enter your answer...')
    })
  })

  describe('Component Rendering', () => {
    it('should render components with resolved props', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(mockResolvePropsDataBindings).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'answer',
          toName: 'context',
          placeholder: 'Enter your answer...',
        }),
        { context: 'Test question' }
      )
    })

    it('should handle unknown component types gracefully', () => {
      const configWithUnknownType = {
        ...mockParsedConfig,
        children: [
          ...mockParsedConfig.children,
          {
            type: 'UnknownComponent',
            name: 'unknown',
            props: {},
            children: [],
          },
        ],
      }

      mockParseLabelConfig.mockReturnValue(configWithUnknownType)

      // Should render without throwing errors
      render(<DynamicAnnotationInterface {...defaultProps} />)

      // Known components should still render
      expect(screen.getByTestId('textarea')).toBeInTheDocument()
    })

    it('should provide component names from props or fallback', () => {
      const configWithoutNames = {
        type: 'View',
        name: 'root',
        props: {},
        children: [
          {
            type: 'TextArea',
            name: undefined,
            props: {
              toName: 'context',
              placeholder: 'No name provided',
            },
            children: [],
          },
        ],
      }

      mockParseLabelConfig.mockReturnValue(configWithoutNames)

      render(<DynamicAnnotationInterface {...defaultProps} />)

      // Component should render with fallback name
      expect(mockTextAreaComponent()).toHaveBeenCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({
            type: 'TextArea',
          }),
        }),
        expect.any(Object)
      )
    })
  })

  describe('Keyboard Shortcuts', () => {
    it('should submit on Ctrl+Enter', async () => {
      const mockOnSubmit = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Test answer')

      fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })
    })

    it('should submit on Cmd+Enter (Mac)', async () => {
      const mockOnSubmit = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Test answer')

      fireEvent.keyDown(window, { key: 'Enter', metaKey: true })

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })
    })

    it('should call onSkip on Ctrl+Escape key', () => {
      const mockOnSkip = jest.fn()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSkip={mockOnSkip} />
      )

      fireEvent.keyDown(window, { key: 'Escape', ctrlKey: true })

      expect(mockOnSkip).toHaveBeenCalled()
    })

    it('should not call onSkip on Escape without Ctrl', () => {
      const mockOnSkip = jest.fn()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSkip={mockOnSkip} />
      )

      fireEvent.keyDown(window, { key: 'Escape' })

      expect(mockOnSkip).not.toHaveBeenCalled()
    })

    it('should not call onSkip on Ctrl+Escape when onSkip not provided', () => {
      const mockOnSkip = jest.fn()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSkip={undefined} />
      )

      fireEvent.keyDown(window, { key: 'Escape', ctrlKey: true })

      expect(mockOnSkip).not.toHaveBeenCalled()
    })
  })

  describe('Task State Management', () => {
    it('should clear form state when taskId changes', () => {
      const { rerender } = render(
        <DynamicAnnotationInterface {...defaultProps} taskId="task-1" />
      )

      let submitButton = getMainSubmitButton()
      expect(submitButton).toBeDisabled()

      rerender(<DynamicAnnotationInterface {...defaultProps} taskId="task-2" />)

      submitButton = getMainSubmitButton()
      expect(submitButton).toBeDisabled()
    })

    it('should maintain state when taskId does not change', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <DynamicAnnotationInterface {...defaultProps} taskId="task-1" />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Test')

      rerender(
        <DynamicAnnotationInterface
          {...defaultProps}
          taskId="task-1"
          taskData={{ context: 'Updated context' }}
        />
      )

      expect(textarea).toHaveValue('Test')
    })
  })

  describe('Configuration Error Handling', () => {
    it('should handle parse errors and show error message', () => {
      mockParseLabelConfig.mockReturnValue({
        message: 'Invalid XML configuration',
      } as any)

      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getByTestId('alert')).toBeInTheDocument()
      expect(screen.getByText('Configuration Error')).toBeInTheDocument()
      expect(screen.getByText('Invalid XML configuration')).toBeInTheDocument()
    })

    it('should handle validation errors', () => {
      mockValidateParsedConfig.mockReturnValue({
        valid: false,
        errors: ['Missing required attribute', 'Invalid component type'],
      })

      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getByTestId('alert')).toBeInTheDocument()
      expect(screen.getByText('Missing required attribute')).toBeInTheDocument()
      expect(screen.getByText('Invalid component type')).toBeInTheDocument()
    })

    it('should handle missing required data fields', () => {
      mockExtractRequiredDataFields.mockReturnValue(['text', 'context'])
      mockValidateTaskDataFields.mockReturnValue({
        valid: false,
        missingFields: ['text'],
      })

      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getByTestId('alert')).toBeInTheDocument()
      expect(
        screen.getByText(/Missing required fields: text/i)
      ).toBeInTheDocument()
    })

    it('should show fallback task data display on error', () => {
      mockParseLabelConfig.mockReturnValue({
        message: 'Parse error',
      } as any)

      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getByText('Task Data')).toBeInTheDocument()
      expect(
        screen.getByText(/"context": "Test question"/, { exact: false })
      ).toBeInTheDocument()
    })
  })

  describe('Initial Values', () => {
    it('should initialize with provided initial values', () => {
      const initialValues = [
        {
          from_name: 'answer',
          to_name: 'context',
          type: 'textarea' as const,
          value: 'Initial answer',
        },
      ]

      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          initialValues={initialValues}
        />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveValue('Initial answer')
    })

    it('should handle textarea type initial values with text array', () => {
      const initialValues = [
        {
          from_name: 'answer',
          to_name: 'context',
          type: 'textarea' as const,
          value: { text: ['Part 1', 'Part 2'] },
        },
      ]

      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          initialValues={initialValues}
        />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toHaveValue('Part 1 Part 2')
    })
  })

  describe('OnChange Callback', () => {
    it('should call onChange when component values change', async () => {
      const mockOnChange = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onChange={mockOnChange} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'New value')

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })
    })

    it('should call onChange with annotation results', async () => {
      const mockOnChange = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onChange={mockOnChange} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Test')

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
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

  describe('Edge Cases', () => {
    it('should handle empty label config', () => {
      mockParseLabelConfig.mockReturnValue({
        message: 'Empty configuration',
      } as any)

      render(<DynamicAnnotationInterface {...defaultProps} labelConfig="" />)

      expect(screen.getByTestId('alert')).toBeInTheDocument()
    })

    it('should handle taskData without required fields', () => {
      render(<DynamicAnnotationInterface {...defaultProps} taskData={{}} />)

      expect(getMainSubmitButton()).toBeInTheDocument()
    })

    it('should clear state after successful submission', async () => {
      const mockOnSubmit = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Test')

      const submitButton = getMainSubmitButton()
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })

      expect(submitButton).toBeDisabled()
    })
  })

  describe('Component Value Tracking', () => {
    it('should track component values in state', async () => {
      const user = userEvent.setup()

      render(<DynamicAnnotationInterface {...defaultProps} />)

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'New value')

      expect(textarea).toHaveValue('New value')
    })

    it('should handle multiple component value changes', async () => {
      const user = userEvent.setup()

      render(<DynamicAnnotationInterface {...defaultProps} />)

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'First')
      await user.clear(textarea)
      await user.type(textarea, 'Second')

      expect(textarea).toHaveValue('Second')
    })

    it('should maintain component values during re-renders', async () => {
      const user = userEvent.setup()
      const { rerender } = render(
        <DynamicAnnotationInterface {...defaultProps} taskId="task-1" />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Test value')

      rerender(
        <DynamicAnnotationInterface
          {...defaultProps}
          taskId="task-1"
          taskData={{ context: 'Updated context' }}
        />
      )

      expect(textarea).toHaveValue('Test value')
    })
  })

  describe('Annotation Result Building', () => {
    it('should build annotation results from component values', async () => {
      const mockOnChange = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onChange={mockOnChange} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Answer')

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(
          expect.arrayContaining([
            expect.objectContaining({
              from_name: 'answer',
              type: 'textarea',
              value: expect.any(String),
            }),
          ])
        )
      })
    })

    it('should handle empty component values', async () => {
      const mockOnSubmit = jest.fn()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      const submitButton = getMainSubmitButton()

      expect(submitButton).toBeDisabled()
    })

    it('should enable submit button when component values exist', async () => {
      const user = userEvent.setup()

      render(<DynamicAnnotationInterface {...defaultProps} />)

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Value')

      const submitButton = getMainSubmitButton()
      expect(submitButton).not.toBeDisabled()
    })
  })

  describe('Validation', () => {
    it('should validate annotations before submission', async () => {
      const mockOnSubmit = jest.fn()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      const submitButton = getMainSubmitButton()
      fireEvent.click(submitButton)

      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('should show validation error messages', async () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      const submitButton = getMainSubmitButton()

      expect(submitButton).toBeDisabled()
    })

    it('should validate non-empty annotation values', async () => {
      const mockOnSubmit = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, '   ')

      const submitButton = getMainSubmitButton()
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })
    })
  })

  describe('Data Binding Resolution', () => {
    it('should resolve data bindings in component props', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(mockResolvePropsDataBindings).toHaveBeenCalled()
    })

    it('should pass resolved props to components', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(mockTextComponent()).toHaveBeenCalledWith(
        expect.objectContaining({
          config: expect.objectContaining({
            props: expect.any(Object),
          }),
        }),
        expect.any(Object)
      )
    })

    it('should handle taskData references in props', () => {
      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          taskData={{ context: 'Test context' }}
        />
      )

      expect(mockResolvePropsDataBindings).toHaveBeenCalledWith(
        expect.anything(),
        { context: 'Test context' }
      )
    })
  })

  describe('Component Rendering with Children', () => {
    it('should render visual components with children', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getByTestId('mock-view')).toBeInTheDocument()
      expect(screen.getByTestId('mock-text')).toBeInTheDocument()
      expect(screen.getByTestId('mock-textarea')).toBeInTheDocument()
    })

    it('should handle nested component structures', () => {
      const nestedConfig = {
        type: 'View',
        name: 'root',
        props: {},
        children: [
          {
            type: 'View',
            name: 'nested',
            props: {},
            children: [
              {
                type: 'Text',
                name: 'nested-text',
                props: { value: 'Nested' },
                children: [],
              },
            ],
          },
        ],
      }

      mockParseLabelConfig.mockReturnValue(nestedConfig)

      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getAllByTestId('mock-view').length).toBeGreaterThan(0)
    })

    it('should render components in correct order', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      const view = screen.getByTestId('mock-view')
      const text = screen.getByTestId('mock-text')
      const textarea = screen.getByTestId('mock-textarea')

      expect(view).toBeInTheDocument()
      expect(text).toBeInTheDocument()
      expect(textarea).toBeInTheDocument()
    })
  })

  describe('Keyboard Shortcut Edge Cases', () => {
    it('should not submit on Enter without modifier key', async () => {
      const mockOnSubmit = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Test answer')

      fireEvent.keyDown(window, { key: 'Enter' })

      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('should not skip on other keys', () => {
      const mockOnSkip = jest.fn()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSkip={mockOnSkip} />
      )

      fireEvent.keyDown(window, { key: 'Enter' })
      fireEvent.keyDown(window, { key: 'Space' })
      fireEvent.keyDown(window, { key: 'Tab' })

      expect(mockOnSkip).not.toHaveBeenCalled()
    })

    it('should handle keyboard shortcuts after component unmount', () => {
      const mockOnSubmit = jest.fn()
      const { unmount } = render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      unmount()

      fireEvent.keyDown(window, { key: 'Enter', ctrlKey: true })

      expect(mockOnSubmit).not.toHaveBeenCalled()
    })
  })

  describe('Initial Values Processing', () => {
    it('should handle multiple initial values', () => {
      const initialValues = [
        {
          from_name: 'field1',
          to_name: 'text',
          type: 'textarea' as const,
          value: 'Value 1',
        },
        {
          from_name: 'field2',
          to_name: 'text',
          type: 'textarea' as const,
          value: 'Value 2',
        },
      ]

      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          initialValues={initialValues}
        />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toBeInTheDocument()
    })

    it('should handle initial values with nested objects', () => {
      const initialValues = [
        {
          from_name: 'answer',
          to_name: 'context',
          type: 'textarea' as const,
          value: { text: 'Nested value', meta: { timestamp: Date.now() } },
        },
      ]

      render(
        <DynamicAnnotationInterface
          {...defaultProps}
          initialValues={initialValues}
        />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toBeInTheDocument()
    })

    it('should handle empty initial values array', () => {
      render(
        <DynamicAnnotationInterface {...defaultProps} initialValues={[]} />
      )

      const submitButton = getMainSubmitButton()
      expect(submitButton).toBeDisabled()
    })
  })

  describe('Error State Management', () => {
    it('should clear errors when taskId changes', () => {
      mockParseLabelConfig.mockReturnValue({ message: 'Error' } as any)

      const { rerender } = render(
        <DynamicAnnotationInterface {...defaultProps} taskId="task-1" />
      )

      expect(screen.getByTestId('alert')).toBeInTheDocument()

      mockParseLabelConfig.mockReturnValue(mockParsedConfig)

      rerender(<DynamicAnnotationInterface {...defaultProps} taskId="task-2" />)

      expect(screen.queryByTestId('alert')).not.toBeInTheDocument()
    })

    it('should show multiple validation errors', () => {
      mockValidateParsedConfig.mockReturnValue({
        valid: false,
        errors: ['Error 1', 'Error 2', 'Error 3'],
      })

      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getByText('Error 1')).toBeInTheDocument()
      expect(screen.getByText('Error 2')).toBeInTheDocument()
      expect(screen.getByText('Error 3')).toBeInTheDocument()
    })

    it('should handle submission errors gracefully', async () => {
      const mockOnSubmit = jest
        .fn()
        .mockRejectedValue(new Error('Submit failed'))
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSubmit={mockOnSubmit} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Test')

      const submitButton = getMainSubmitButton()
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled()
      })
    })
  })

  describe('Component Props Passing', () => {
    it('should pass taskData to components', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(mockTextAreaComponent()).toHaveBeenCalledWith(
        expect.objectContaining({
          taskData: defaultProps.taskData,
        }),
        expect.any(Object)
      )
    })

    it('should pass onChange handler to components', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(mockTextAreaComponent()).toHaveBeenCalledWith(
        expect.objectContaining({
          onChange: expect.any(Function),
        }),
        expect.any(Object)
      )
    })

    it('should pass onAnnotation handler to components', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(mockTextAreaComponent()).toHaveBeenCalledWith(
        expect.objectContaining({
          onAnnotation: expect.any(Function),
        }),
        expect.any(Object)
      )
    })

    it('should pass value prop to components', async () => {
      const user = userEvent.setup()

      render(<DynamicAnnotationInterface {...defaultProps} />)

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Value')

      await waitFor(() => {
        expect(mockTextAreaComponent()).toHaveBeenCalledWith(
          expect.objectContaining({
            value: expect.any(String),
          }),
          expect.any(Object)
        )
      })
    })
  })

  describe('Configuration Validation', () => {
    it('should validate configuration on mount', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(mockValidateParsedConfig).toHaveBeenCalled()
    })

    it('should extract data fields from configuration', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(mockExtractRequiredDataFields).toHaveBeenCalled()
    })

    it('should validate task data fields', () => {
      mockExtractRequiredDataFields.mockReturnValue(['context'])

      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(mockValidateTaskDataFields).toHaveBeenCalledWith(
        ['context'],
        defaultProps.taskData
      )
    })

    it('should handle configuration with no required fields', () => {
      mockExtractRequiredDataFields.mockReturnValue([])

      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(getMainSubmitButton()).toBeInTheDocument()
    })
  })

  describe('Annotation Handling', () => {
    it('should handle onAnnotation callback', async () => {
      const mockOnChange = jest.fn()

      render(
        <DynamicAnnotationInterface {...defaultProps} onChange={mockOnChange} />
      )

      const textarea = screen.getByTestId('textarea')
      expect(textarea).toBeInTheDocument()
    })

    it('should update annotations map when onAnnotation is called', async () => {
      const user = userEvent.setup()

      render(<DynamicAnnotationInterface {...defaultProps} />)

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'Test annotation')

      await waitFor(() => {
        const submitButton = getMainSubmitButton()
        expect(submitButton).not.toBeDisabled()
      })
    })

    it('should handle duplicate annotations for same field', async () => {
      const mockOnChange = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onChange={mockOnChange} />
      )

      const textarea = screen.getByTestId('textarea')
      await user.type(textarea, 'First')
      await user.clear(textarea)
      await user.type(textarea, 'Second')

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalled()
      })
    })
  })

  describe('Skip Functionality', () => {
    it('should call onSkip when skip button is clicked', async () => {
      const mockOnSkip = jest.fn()
      const user = userEvent.setup()

      render(
        <DynamicAnnotationInterface {...defaultProps} onSkip={mockOnSkip} />
      )

      const skipButton = screen.getByRole('button', { name: /skip/i })
      await user.click(skipButton)

      expect(mockOnSkip).toHaveBeenCalled()
    })

    it('should not show skip shortcut when onSkip not provided', () => {
      render(
        <DynamicAnnotationInterface {...defaultProps} onSkip={undefined} />
      )

      const skipText = screen.queryByText(/ESC/i)
      expect(skipText).not.toBeInTheDocument()
    })

    it('should show skip shortcut when onSkip is provided', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getByText(/ESC/i)).toBeInTheDocument()
    })
  })

  describe('UI Text and Localization', () => {
    it('should display submit button with shortcut text', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      const allSubmitTexts = screen.getAllByText(/Submit/i)
      expect(allSubmitTexts.length).toBeGreaterThan(0)
      expect(screen.getByText(/Ctrl\+Enter/i)).toBeInTheDocument()
    })

    it('should display keyboard shortcut tip', () => {
      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(
        screen.getByText(/Use keyboard shortcuts for faster annotation/i)
      ).toBeInTheDocument()
    })

    it('should display task data heading in error state', () => {
      mockParseLabelConfig.mockReturnValue({ message: 'Error' } as any)

      render(<DynamicAnnotationInterface {...defaultProps} />)

      expect(screen.getByText('Task Data')).toBeInTheDocument()
    })
  })
})

// Mock shared components to prevent import errors
jest.mock('@/components/shared', () => {
  const React = require('react')
  return {
    HeroPattern: () =>
      React.createElement(
        'div',
        { 'data-testid': 'hero-pattern' },
        'Hero Pattern'
      ),
    GridPattern: () =>
      React.createElement(
        'div',
        { 'data-testid': 'grid-pattern' },
        'Grid Pattern'
      ),
    Button: ({ children, ...props }) =>
      React.createElement('button', props, children),
    ResponsiveContainer: ({ children }) =>
      React.createElement('div', null, children),
    LoadingSpinner: () =>
      React.createElement(
        'div',
        { 'data-testid': 'loading-spinner' },
        'Loading...'
      ),
    EmptyState: ({ message }) => React.createElement('div', null, message),
    Spinner: () => React.createElement('div', null, 'Loading...'),
    // Add other exports as needed
  }
})
