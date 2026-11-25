/**
 * Simple integration test for DynamicAnnotationInterface hideSubmitButton functionality
 * Tests that hideSubmitButton prop is properly passed to components to resolve issue #251, #1030
 *
 * Correct behavior: components always get hideSubmitButton=true. A field's own
 * submit button only rebuilds that field's result and saves nothing, so it is
 * never shown inside the form: with the main button shown it would duplicate
 * it, and with the main button hidden the host submits through its own
 * controls (for example the review page's action bar).
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { DynamicAnnotationInterface } from '../DynamicAnnotationInterface'

// Mock I18n context FIRST
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'annotation.interface.configError': 'Configuration Error',
        'annotation.interface.missingFields':
          'Missing required fields: {fields}',
        'annotation.interface.atLeastOne':
          'At least one annotation is required',
        'annotation.interface.fieldRequired': 'Field "{fieldName}" is required',
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

// Mock shared components
jest.mock('@/components/shared/Alert', () => ({
  Alert: ({ children }: any) => <div data-testid="alert">{children}</div>,
}))

jest.mock('@/components/shared/Skeleton', () => ({
  Skeleton: (props: any) => <div data-testid="skeleton" {...props} />,
}))

// Create mock component that we can track
const MockTextAreaComponent = jest.fn(
  ({ hideSubmitButton, config, value, onChange }: any) => (
    <div data-testid="mock-textarea-container">
      <textarea
        data-testid="textarea"
        value={value || ''}
        onChange={(e) => onChange?.(e.target.value)}
        placeholder={config?.props?.placeholder || 'Enter text'}
      />
      {!hideSubmitButton && (
        <button data-testid="component-submit-button">Component Submit</button>
      )}
    </div>
  ),
)

// Mock the registry
jest.mock('@/lib/labelConfig/registry', () => ({
  getComponent: jest.fn((type: string) => {
    if (type === 'TextArea') {
      return {
        component: MockTextAreaComponent,
        category: 'control',
      }
    }
    if (type === 'View') {
      return {
        component: ({ children }: any) => (
          <div data-testid="mock-view">{children}</div>
        ),
        category: 'visual',
      }
    }
    return null
  }),
}))

// Mock the parser
jest.mock('@/lib/labelConfig/parser', () => ({
  parseLabelConfig: jest.fn(() => ({
    type: 'View',
    name: 'root',
    props: {},
    children: [
      {
        type: 'TextArea',
        name: 'answer',
        props: {
          name: 'answer',
          placeholder: 'Enter your answer',
        },
        children: [],
      },
    ],
  })),
  validateParsedConfig: jest.fn(() => ({ valid: true, errors: [] })),
  extractDataFields: jest.fn(() => []),
  extractRequiredDataFields: jest.fn(() => []),
}))

// Mock data binding
jest.mock('@/lib/labelConfig/dataBinding', () => ({
  resolvePropsDataBindings: jest.fn((props: any) => props),
  validateTaskDataFields: jest.fn(() => ({ valid: true, missingFields: [] })),
  buildAnnotationResult: jest.fn(
    (name: string, type: string, value: any, toName: string) => ({
      from_name: name,
      to_name: toName,
      type,
      value,
    }),
  ),
}))

describe('DynamicAnnotationInterface hideSubmitButton Integration', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should pass hideSubmitButton=true to components when showSubmitButton=true (default) - Issue #1030 fix', () => {
    const props = {
      labelConfig: '<TextArea name="answer" placeholder="Enter your answer" />',
      taskData: {},
      onSubmit: jest.fn(),
      onSkip: jest.fn(),
      showSubmitButton: true,
    }

    render(<DynamicAnnotationInterface {...props} />)

    // Verify the main interface submit button is present
    const mainSubmitButton = screen.getByRole('button', { name: /submit/i })
    expect(mainSubmitButton).toBeInTheDocument()

    // When showSubmitButton=true, hideSubmitButton=true, so component buttons are hidden
    // This prevents duplicate submit buttons (Issue #1030)
    const componentSubmitButton = screen.queryByTestId(
      'component-submit-button',
    )
    expect(componentSubmitButton).not.toBeInTheDocument()

    // Verify our mock component was called with hideSubmitButton=true
    expect(MockTextAreaComponent).toHaveBeenCalledWith(
      expect.objectContaining({
        hideSubmitButton: true,
      }),
      undefined,
    )
  })

  it('should pass hideSubmitButton=true when showSubmitButton=false (host submits)', () => {
    const props = {
      labelConfig: '<TextArea name="answer" placeholder="Enter your answer" />',
      taskData: {},
      onSubmit: jest.fn(),
      onSkip: jest.fn(),
      showSubmitButton: false,
    }

    render(<DynamicAnnotationInterface {...props} />)

    // Verify the main interface submit button (with shortcut hint) is NOT present
    // The main button contains "Ctrl+Enter" shortcut text
    const mainSubmitButton = screen.queryByText(/Ctrl\+Enter/i)
    expect(mainSubmitButton).not.toBeInTheDocument()

    // The host hides the main button because it submits itself, so the
    // component's own button (which saves nothing) stays hidden too
    const componentSubmitButton = screen.queryByTestId(
      'component-submit-button',
    )
    expect(componentSubmitButton).not.toBeInTheDocument()

    expect(MockTextAreaComponent).not.toHaveBeenCalledWith(
      expect.objectContaining({
        hideSubmitButton: false,
      }),
      undefined,
    )
  })

  it('should display only main submit button when showSubmitButton=true (default behavior)', () => {
    const props = {
      labelConfig: '<TextArea name="answer" />',
      taskData: {},
      onSubmit: jest.fn(),
    }

    render(<DynamicAnnotationInterface {...props} />)

    // Only the main submit button should be present, not the component button
    const submitButtons = screen.getAllByRole('button', { name: /submit/i })
    expect(submitButtons.length).toBe(1)

    // The main interface submit button should have emerald styling
    expect(submitButtons[0]).toHaveClass('bg-zinc-900')

    // Component submit button should NOT be present
    const componentSubmitButton = screen.queryByTestId(
      'component-submit-button',
    )
    expect(componentSubmitButton).not.toBeInTheDocument()
  })
})
