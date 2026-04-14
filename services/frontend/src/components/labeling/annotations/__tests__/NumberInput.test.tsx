/**
 * Comprehensive tests for NumberInput component
 * Tests number entry, validation, min/max bounds, and format handling
 */

/**
 * @jest-environment jsdom
 */

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'annotation.numberPlaceholder': 'Enter a number...',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock Label component
jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, htmlFor }: any) => (
    <label data-testid="label" htmlFor={htmlFor}>
      {children}
    </label>
  ),
}))

// Mock Input component
jest.mock('@/components/shared/Input', () => {
  const React = require('react')
  const Input = React.forwardRef(function Input(props: any, ref: any) {
    return <input ref={ref} {...props} data-testid="number-input" />
  })
  Input.displayName = 'Input'
  return { Input }
})

// Mock data binding utilities
const mockBuildAnnotationResult = jest.fn((name, type, value, toName) => ({
  from_name: name,
  to_name: toName,
  type,
  value,
}))

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  buildAnnotationResult: (...args: any[]) => mockBuildAnnotationResult(...args),
}))

// Import the component after mocks
import NumberInput from '../NumberInput'

describe('NumberInput', () => {
  const mockOnChange = jest.fn()
  const mockOnAnnotation = jest.fn()

  const defaultConfig = {
    type: 'Number',
    name: 'score',
    props: {
      name: 'score',
      toName: 'text',
      label: 'Enter Score',
      min: '0',
      max: '100',
      step: '1',
      required: 'false',
      placeholder: 'Enter a number...',
    },
    children: [],
  }

  const defaultProps = {
    config: defaultConfig,
    taskData: { text: 'Sample text' },
    value: undefined,
    onChange: mockOnChange,
    onAnnotation: mockOnAnnotation,
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders with label', () => {
      render(<NumberInput {...defaultProps} />)

      expect(screen.getByText('Enter Score')).toBeInTheDocument()
    })

    it('renders input field', () => {
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('type', 'number')
    })

    it('renders required asterisk when required', () => {
      const requiredConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, required: 'true' },
      }

      render(<NumberInput {...defaultProps} config={requiredConfig} />)

      expect(screen.getByText('*')).toBeInTheDocument()
    })

    it('renders hint when provided', () => {
      const configWithHint = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          hint: 'Enter a value between 0 and 100',
        },
      }

      render(<NumberInput {...defaultProps} config={configWithHint} />)

      expect(
        screen.getByText('Enter a value between 0 and 100')
      ).toBeInTheDocument()
    })

    it('uses fallback label when label not provided', () => {
      const configWithoutLabel = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          label: undefined,
        },
      }

      render(<NumberInput {...defaultProps} config={configWithoutLabel} />)

      expect(screen.getByText('score')).toBeInTheDocument()
    })

    it('uses name as fallback when both label and name not in props', () => {
      const configWithOnlyTypeName = {
        ...defaultConfig,
        name: 'fallback-number',
        props: {
          toName: 'text',
        },
      }

      render(<NumberInput {...defaultProps} config={configWithOnlyTypeName} />)

      expect(screen.getByText('fallback-number')).toBeInTheDocument()
    })

    it('uses number as default name when all name sources missing', () => {
      const config = {
        type: 'Number',
        props: {
          toName: 'text',
        },
        children: [],
      }

      render(<NumberInput {...defaultProps} config={config as any} />)

      expect(screen.getByText('number')).toBeInTheDocument()
    })
  })

  describe('Number Entry', () => {
    it('accepts numeric input', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '42')

      expect(input).toHaveValue(42)
    })

    it('calls onChange when number is entered', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '75')

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(75)
      })
    })

    it('calls onAnnotation when number is entered', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '50')

      await waitFor(() => {
        expect(mockOnAnnotation).toHaveBeenCalledWith({
          from_name: 'score',
          to_name: 'text',
          type: 'Number',
          value: 50,
        })
      })
    })

    it('accepts decimal numbers', async () => {
      const user = userEvent.setup()
      const configWithDecimals = {
        ...defaultConfig,
        props: { ...defaultConfig.props, step: '0.1' },
      }

      render(<NumberInput {...defaultProps} config={configWithDecimals} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '3.14')

      expect(input).toHaveValue(3.14)
    })

    it('accepts negative numbers', async () => {
      const user = userEvent.setup()
      const configWithNegatives = {
        ...defaultConfig,
        props: { ...defaultConfig.props, min: '-100' },
      }

      render(<NumberInput {...defaultProps} config={configWithNegatives} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '-25')

      expect(input).toHaveValue(-25)
    })

    it('handles zero input', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '0')

      expect(input).toHaveValue(0)
      expect(mockOnChange).toHaveBeenCalledWith(0)
    })
  })

  describe('Validation', () => {
    it('does not call onChange for invalid input', async () => {
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')

      // Clear any previous calls
      mockOnChange.mockClear()

      // Try to enter non-numeric characters (browser handles this at input level)
      fireEvent.change(input, { target: { value: 'abc' } })

      // onChange should be called but with NaN, which we don't propagate
      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('handles empty input gracefully', () => {
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      fireEvent.change(input, { target: { value: '' } })

      expect(input).toHaveValue(null)
      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('marks input as required when required=true', () => {
      const requiredConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, required: 'true' },
      }

      render(<NumberInput {...defaultProps} config={requiredConfig} />)

      const input = screen.getByTestId('number-input')
      expect(input).toBeRequired()
    })

    it('does not mark input as required when required=false', () => {
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      expect(input).not.toBeRequired()
    })
  })

  describe('Min/Max Bounds', () => {
    it('applies min attribute', () => {
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('min', '0')
    })

    it('applies max attribute', () => {
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('max', '100')
    })

    it('accepts value at minimum bound', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '0')

      expect(input).toHaveValue(0)
      expect(mockOnChange).toHaveBeenCalledWith(0)
    })

    it('accepts value at maximum bound', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      await user.clear(input)
      await user.type(input, '100')

      await waitFor(() => {
        expect(mockOnChange).toHaveBeenCalledWith(100)
      })
    })

    it('handles missing min attribute', () => {
      const configWithoutMin = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          min: undefined,
        },
      }

      render(<NumberInput {...defaultProps} config={configWithoutMin} />)

      const input = screen.getByTestId('number-input')
      expect(input).not.toHaveAttribute('min')
    })

    it('handles missing max attribute', () => {
      const configWithoutMax = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          max: undefined,
        },
      }

      render(<NumberInput {...defaultProps} config={configWithoutMax} />)

      const input = screen.getByTestId('number-input')
      expect(input).not.toHaveAttribute('max')
    })
  })

  describe('Step Handling', () => {
    it('applies step attribute', () => {
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('step', '1')
    })

    it('uses default step of 1 when not provided', () => {
      const configWithoutStep = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          step: undefined,
        },
      }

      render(<NumberInput {...defaultProps} config={configWithoutStep} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('step', '1')
    })

    it('handles decimal step', () => {
      const configWithDecimalStep = {
        ...defaultConfig,
        props: { ...defaultConfig.props, step: '0.01' },
      }

      render(<NumberInput {...defaultProps} config={configWithDecimalStep} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('step', '0.01')
    })

    it('handles large step values', () => {
      const configWithLargeStep = {
        ...defaultConfig,
        props: { ...defaultConfig.props, step: '10' },
      }

      render(<NumberInput {...defaultProps} config={configWithLargeStep} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('step', '10')
    })
  })

  describe('Placeholder', () => {
    it('displays placeholder text', () => {
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('placeholder', 'Enter a number...')
    })

    it('uses custom placeholder', () => {
      const configWithCustomPlaceholder = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          placeholder: 'Type your score here',
        },
      }

      render(
        <NumberInput {...defaultProps} config={configWithCustomPlaceholder} />
      )

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('placeholder', 'Type your score here')
    })

    it('uses default placeholder when not provided', () => {
      const configWithoutPlaceholder = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          placeholder: undefined,
        },
      }

      render(
        <NumberInput {...defaultProps} config={configWithoutPlaceholder} />
      )

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('placeholder', 'Enter a number...')
    })
  })

  describe('External Value Control', () => {
    it('displays initial external value when provided', () => {
      render(<NumberInput {...defaultProps} value={42} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveValue(42)
    })

    it('maintains internal state after initialization', () => {
      const { rerender } = render(<NumberInput {...defaultProps} value={10} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveValue(10)

      // Note: Component uses useState and doesn't sync with external value changes
      // This is the current behavior - internal state is independent after mount
      rerender(<NumberInput {...defaultProps} value={25} />)
      expect(input).toHaveValue(10) // Still shows initial value
    })

    it('handles undefined external value', () => {
      render(<NumberInput {...defaultProps} value={undefined} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveValue(null)
    })

    it('handles null external value', () => {
      render(<NumberInput {...defaultProps} value={null} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveValue(null)
    })

    it('converts initial external value to string for display', () => {
      render(<NumberInput {...defaultProps} value={3.14159} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveValue(3.14159)
    })
  })

  describe('Annotation Creation', () => {
    it('does not call onAnnotation when toName is not provided', async () => {
      const user = userEvent.setup()
      const configWithoutToName = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          toName: undefined,
        },
      }

      render(<NumberInput {...defaultProps} config={configWithoutToName} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '42')

      expect(mockOnAnnotation).not.toHaveBeenCalled()
    })

    it('creates annotation with correct structure', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '88')

      await waitFor(() => {
        expect(mockBuildAnnotationResult).toHaveBeenCalledWith(
          'score',
          'Number',
          88,
          'text'
        )
      })
    })

    it('creates annotation for decimal values', async () => {
      const user = userEvent.setup()
      const configWithDecimals = {
        ...defaultConfig,
        props: { ...defaultConfig.props, step: '0.1' },
      }

      render(<NumberInput {...defaultProps} config={configWithDecimals} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '2.5')

      await waitFor(() => {
        expect(mockOnAnnotation).toHaveBeenCalledWith({
          from_name: 'score',
          to_name: 'text',
          type: 'Number',
          value: 2.5,
        })
      })
    })

    it('creates annotation for zero', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '0')

      await waitFor(() => {
        expect(mockOnAnnotation).toHaveBeenCalledWith({
          from_name: 'score',
          to_name: 'text',
          type: 'Number',
          value: 0,
        })
      })
    })

    it('creates annotation for negative numbers', async () => {
      const user = userEvent.setup()
      const configWithNegatives = {
        ...defaultConfig,
        props: { ...defaultConfig.props, min: '-100' },
      }

      render(<NumberInput {...defaultProps} config={configWithNegatives} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '-15')

      await waitFor(() => {
        expect(mockOnAnnotation).toHaveBeenCalledWith({
          from_name: 'score',
          to_name: 'text',
          type: 'Number',
          value: -15,
        })
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles very large numbers', async () => {
      const user = userEvent.setup()
      const configWithLargeMax = {
        ...defaultConfig,
        props: { ...defaultConfig.props, max: '999999999' },
      }

      render(<NumberInput {...defaultProps} config={configWithLargeMax} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '123456789')

      expect(input).toHaveValue(123456789)
    })

    it('handles very small numbers', async () => {
      const user = userEvent.setup()
      const configWithSmallStep = {
        ...defaultConfig,
        props: { ...defaultConfig.props, step: '0.00001' },
      }

      render(<NumberInput {...defaultProps} config={configWithSmallStep} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '0.00042')

      expect(input).toHaveValue(0.00042)
    })

    it('handles rapid value changes', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')

      await user.type(input, '1')
      await user.clear(input)
      await user.type(input, '2')
      await user.clear(input)
      await user.type(input, '3')

      expect(input).toHaveValue(3)
    })

    it('handles scientific notation', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')

      // Directly change value as user typing might not work for scientific notation
      fireEvent.change(input, { target: { value: '1e5' } })

      expect(mockOnChange).toHaveBeenCalledWith(100000)
    })

    it('clears value correctly', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} value={50} />)

      const input = screen.getByTestId('number-input')
      await user.clear(input)

      expect(input).toHaveValue(null)
    })
  })

  describe('Accessibility', () => {
    it('associates label with input using htmlFor', () => {
      render(<NumberInput {...defaultProps} />)

      const label = screen.getByTestId('label')
      const input = screen.getByTestId('number-input')

      expect(label).toHaveAttribute('for', 'score')
      expect(input).toHaveAttribute('id', 'score')
    })

    it('input is keyboard accessible', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')

      await user.tab()
      expect(input).toHaveFocus()
    })

    it('has correct input type for assistive technologies', () => {
      render(<NumberInput {...defaultProps} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveAttribute('type', 'number')
    })
  })

  describe('Multiple Instances', () => {
    it('handles multiple NumberInput components independently', async () => {
      const user = userEvent.setup()
      const mockOnChange1 = jest.fn()
      const mockOnChange2 = jest.fn()

      const props1 = {
        ...defaultProps,
        config: {
          ...defaultConfig,
          props: { ...defaultConfig.props, name: 'number1' },
        },
        onChange: mockOnChange1,
      }

      const props2 = {
        ...defaultProps,
        config: {
          ...defaultConfig,
          props: { ...defaultConfig.props, name: 'number2' },
        },
        onChange: mockOnChange2,
      }

      render(
        <div>
          <NumberInput {...props1} />
          <NumberInput {...props2} />
        </div>
      )

      const inputs = screen.getAllByTestId('number-input')

      await user.type(inputs[0], '10')
      await user.type(inputs[1], '20')

      await waitFor(() => {
        expect(mockOnChange1).toHaveBeenCalledWith(10)
        expect(mockOnChange2).toHaveBeenCalledWith(20)
      })
    })
  })

  describe('State Management', () => {
    it('maintains internal state when external value not provided', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} value={undefined} />)

      const input = screen.getByTestId('number-input')
      await user.type(input, '77')

      expect(input).toHaveValue(77)
    })

    it('initializes with external value', () => {
      render(<NumberInput {...defaultProps} value={5} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveValue(5)
    })

    it('maintains internal state independent of external value changes', () => {
      const { rerender } = render(
        <NumberInput {...defaultProps} value={undefined} />
      )

      const input = screen.getByTestId('number-input')
      expect(input).toHaveValue(null)

      // External value doesn't sync after mount - this is current behavior
      rerender(<NumberInput {...defaultProps} value={42} />)
      expect(input).toHaveValue(null)
    })

    it('uses initial value for state initialization', () => {
      render(<NumberInput {...defaultProps} value={42} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveValue(42)
    })

    it('allows user input to override initial value', async () => {
      const user = userEvent.setup()
      render(<NumberInput {...defaultProps} value={10} />)

      const input = screen.getByTestId('number-input')
      expect(input).toHaveValue(10)

      await user.clear(input)
      await user.type(input, '99')
      expect(input).toHaveValue(99)
    })
  })
})
