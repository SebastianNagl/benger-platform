/**
 * Tests for LikertInput component
 * Tests Likert scale rendering, value changes, annotation creation
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'

// Mock LikertScale shared component
jest.mock('@/components/shared/LikertScale', () => ({
  LikertScale: ({ name, label, value, onChange, required, min, max }: any) => (
    <fieldset data-testid="likert-scale">
      <legend>{label}{required && <span>*</span>}</legend>
      {Array.from({ length: (max || 7) - (min || 1) + 1 }, (_, i) => (min || 1) + i).map(
        (point: number) => (
          <button
            key={point}
            type="button"
            data-testid={`likert-${point}`}
            data-selected={value === point}
            onClick={() => onChange(point)}
          >
            {point}
          </button>
        )
      )}
    </fieldset>
  ),
}))

// Mock data binding
const mockBuildAnnotationResult = jest.fn((name, type, value, toName) => ({
  from_name: name,
  to_name: toName,
  type,
  value,
}))

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  buildAnnotationResult: (...args: any[]) => mockBuildAnnotationResult(...args),
}))

import LikertInput from '../LikertInput'

describe('LikertInput', () => {
  const defaultProps = {
    config: {
      type: 'Likert',
      name: 'likert',
      props: {
        name: 'agreement',
        toName: 'statement',
        label: 'How much do you agree?',
        min: '1',
        max: '7',
        required: 'false',
      },
      children: [],
    },
    taskData: { statement: 'The sky is blue' },
    value: undefined,
    onChange: jest.fn(),
    onAnnotation: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders the likert scale', () => {
      render(<LikertInput {...defaultProps} />)
      expect(screen.getByTestId('likert-scale')).toBeInTheDocument()
    })

    it('passes label to LikertScale', () => {
      render(<LikertInput {...defaultProps} />)
      expect(screen.getByText('How much do you agree?')).toBeInTheDocument()
    })

    it('renders 7 points by default (1-7)', () => {
      render(<LikertInput {...defaultProps} />)
      for (let i = 1; i <= 7; i++) {
        expect(screen.getByTestId(`likert-${i}`)).toBeInTheDocument()
      }
    })

    it('renders custom min/max range', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: { ...defaultProps.config.props, min: '1', max: '5' },
        },
      }
      render(<LikertInput {...props} />)
      for (let i = 1; i <= 5; i++) {
        expect(screen.getByTestId(`likert-${i}`)).toBeInTheDocument()
      }
    })

    it('renders hint when provided', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: { ...defaultProps.config.props, hint: 'Select your agreement level' },
        },
      }
      render(<LikertInput {...props} />)
      expect(screen.getByText('Select your agreement level')).toBeInTheDocument()
    })

    it('does not render hint when not provided', () => {
      const { container } = render(<LikertInput {...defaultProps} />)
      const hintElements = container.querySelectorAll('.text-zinc-500')
      // No hint paragraph (only the likert scale legend may have zinc-500)
      const hintTexts = Array.from(hintElements).filter((el) =>
        el.tagName.toLowerCase() === 'p'
      )
      expect(hintTexts).toHaveLength(0)
    })
  })

  describe('Value Selection', () => {
    it('calls onChange when a value is selected', () => {
      render(<LikertInput {...defaultProps} />)
      fireEvent.click(screen.getByTestId('likert-4'))
      expect(defaultProps.onChange).toHaveBeenCalledWith(4)
    })

    it('calls onAnnotation with correct structure when value selected', () => {
      render(<LikertInput {...defaultProps} />)
      fireEvent.click(screen.getByTestId('likert-5'))

      expect(defaultProps.onAnnotation).toHaveBeenCalledWith({
        from_name: 'agreement',
        to_name: 'statement',
        type: 'Likert',
        value: 5,
      })
    })

    it('does not call onAnnotation when toName is not provided', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: { ...defaultProps.config.props, toName: undefined },
        },
      }
      render(<LikertInput {...props} />)
      fireEvent.click(screen.getByTestId('likert-3'))

      expect(defaultProps.onChange).toHaveBeenCalledWith(3)
      expect(defaultProps.onAnnotation).not.toHaveBeenCalled()
    })
  })

  describe('Name Resolution', () => {
    it('uses props.name as primary name source', () => {
      render(<LikertInput {...defaultProps} />)
      fireEvent.click(screen.getByTestId('likert-2'))

      expect(mockBuildAnnotationResult).toHaveBeenCalledWith(
        'agreement',
        'Likert',
        2,
        'statement'
      )
    })

    it('falls back to config.name when props.name is not set', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          name: 'fallback-likert',
          props: { ...defaultProps.config.props, name: undefined },
        },
      }
      render(<LikertInput {...props} />)
      fireEvent.click(screen.getByTestId('likert-1'))

      expect(mockBuildAnnotationResult).toHaveBeenCalledWith(
        'fallback-likert',
        'Likert',
        1,
        'statement'
      )
    })

    it('falls back to "likert" when no name is available', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          name: undefined as any,
          props: { toName: 'statement', label: 'Test' },
        },
      }
      render(<LikertInput {...props} />)
      fireEvent.click(screen.getByTestId('likert-1'))

      expect(mockBuildAnnotationResult).toHaveBeenCalledWith(
        'likert',
        'Likert',
        1,
        'statement'
      )
    })
  })

  describe('Initial Value', () => {
    it('initializes with external value when provided', () => {
      const props = { ...defaultProps, value: 4 }
      render(<LikertInput {...props} />)
      // The button with value 4 should have data-selected="true"
      expect(screen.getByTestId('likert-4')).toHaveAttribute('data-selected', 'true')
    })

    it('initializes as undefined when no external value', () => {
      render(<LikertInput {...defaultProps} />)
      // No button should have data-selected="true"
      for (let i = 1; i <= 7; i++) {
        expect(screen.getByTestId(`likert-${i}`)).toHaveAttribute('data-selected', 'false')
      }
    })
  })
})
