/**
 * Comprehensive tests for ChoicesInput component
 * Tests radio and checkbox functionality, choice selection, and layouts
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock Label component
jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, htmlFor }: any) => (
    <label data-testid="label" htmlFor={htmlFor}>
      {children}
    </label>
  ),
}))

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

// Import the actual component
import ChoicesInput from '../ChoicesInput'

describe('ChoicesInput', () => {
  const mockOnChange = jest.fn()
  const mockOnAnnotation = jest.fn()

  // Helper to get choice input by option number (works for both radio and checkbox)
  const getChoiceInput = (optionNumber: number) => {
    const optionText = `Option ${optionNumber}`
    try {
      return screen.getByRole('radio', { name: new RegExp(optionText, 'i') })
    } catch {
      return screen.getByRole('checkbox', { name: new RegExp(optionText, 'i') })
    }
  }

  const defaultConfig = {
    type: 'Choices',
    name: 'category',
    props: {
      name: 'category',
      toName: 'text',
      label: 'Select Category',
      choice: 'single',
      required: 'false',
      layout: 'vertical',
    },
    children: [
      {
        type: 'Choice',
        props: { value: 'option1', alias: 'Option 1' },
      },
      {
        type: 'Choice',
        props: { value: 'option2', alias: 'Option 2' },
      },
      {
        type: 'Choice',
        props: { value: 'option3', alias: 'Option 3' },
      },
    ],
  }

  const defaultProps = {
    config: defaultConfig,
    taskData: { text: 'Sample text' },
    value: null,
    onChange: mockOnChange,
    onAnnotation: mockOnAnnotation,
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders with label', () => {
      render(<ChoicesInput {...defaultProps} />)

      expect(screen.getByText('Select Category')).toBeInTheDocument()
    })

    it('renders all choice options', () => {
      render(<ChoicesInput {...defaultProps} />)

      expect(screen.getByText('Option 1')).toBeInTheDocument()
      expect(screen.getByText('Option 2')).toBeInTheDocument()
      expect(screen.getByText('Option 3')).toBeInTheDocument()
    })

    it('renders required asterisk when required', () => {
      const requiredConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, required: 'true' },
      }

      render(<ChoicesInput {...defaultProps} config={requiredConfig} />)

      expect(screen.getByText('*')).toBeInTheDocument()
    })

    it('renders hint when provided', () => {
      const configWithHint = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          hint: 'Please select one option',
        },
      }

      render(<ChoicesInput {...defaultProps} config={configWithHint} />)

      expect(screen.getByText('Please select one option')).toBeInTheDocument()
    })

    it('uses fallback label when label not provided', () => {
      const configWithoutLabel = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          label: undefined,
        },
      }

      render(<ChoicesInput {...defaultProps} config={configWithoutLabel} />)

      expect(screen.getByText('category')).toBeInTheDocument()
    })
  })

  describe('Single Choice (Radio) Mode', () => {
    it('renders radio buttons for single choice', () => {
      render(<ChoicesInput {...defaultProps} />)

      const radio1 = screen.getByRole('radio', { name: /Option 1/i })
      const radio2 = screen.getByRole('radio', { name: /Option 2/i })

      expect(radio1).toHaveAttribute('type', 'radio')
      expect(radio2).toHaveAttribute('type', 'radio')
    })

    it('allows selecting one option', async () => {
      const user = userEvent.setup()
      render(<ChoicesInput {...defaultProps} />)

      const option1 = screen.getByRole('radio', { name: /Option 1/i })
      await user.click(option1)

      expect(option1).toBeChecked()
      expect(mockOnChange).toHaveBeenCalledWith('option1')
    })

    it('deselects previous option when selecting new option', async () => {
      const user = userEvent.setup()
      render(<ChoicesInput {...defaultProps} />)

      const option1 = getChoiceInput(1)
      const option2 = getChoiceInput(2)

      await user.click(option1)
      expect(option1).toBeChecked()

      await user.click(option2)
      expect(option2).toBeChecked()
      expect(option1).not.toBeChecked()
    })

    it('calls onAnnotation with single value', async () => {
      const user = userEvent.setup()
      render(<ChoicesInput {...defaultProps} />)

      const option1 = getChoiceInput(1)
      await user.click(option1)

      expect(mockOnAnnotation).toHaveBeenCalledWith({
        from_name: 'category',
        to_name: 'text',
        type: 'Choices',
        value: 'option1',
      })
    })

    it('does not call onChange when clicking already selected radio', async () => {
      render(<ChoicesInput {...defaultProps} value="option1" />)

      const option1 = getChoiceInput(1)
      expect(option1).toBeChecked()

      mockOnChange.mockClear()
      fireEvent.click(option1)

      // Clicking an already-selected radio button should not trigger onChange
      // This is standard HTML behavior
      expect(mockOnChange).not.toHaveBeenCalled()
    })
  })

  describe('Multiple Choice (Checkbox) Mode', () => {
    const multipleConfig = {
      ...defaultConfig,
      props: { ...defaultConfig.props, choice: 'multiple' },
    }

    it('renders checkboxes for multiple choice', () => {
      render(<ChoicesInput {...defaultProps} config={multipleConfig} />)

      const checkbox1 = getChoiceInput(1)
      const checkbox2 = getChoiceInput(2)

      expect(checkbox1).toHaveAttribute('type', 'checkbox')
      expect(checkbox2).toHaveAttribute('type', 'checkbox')
    })

    it('allows selecting multiple options', async () => {
      const user = userEvent.setup()
      render(<ChoicesInput {...defaultProps} config={multipleConfig} />)

      const option1 = getChoiceInput(1)
      const option2 = getChoiceInput(2)

      await user.click(option1)
      await user.click(option2)

      expect(option1).toBeChecked()
      expect(option2).toBeChecked()
    })

    it('calls onChange with array of values', async () => {
      const user = userEvent.setup()
      render(<ChoicesInput {...defaultProps} config={multipleConfig} />)

      const option1 = getChoiceInput(1)
      const option2 = getChoiceInput(2)

      await user.click(option1)
      expect(mockOnChange).toHaveBeenCalledWith(['option1'])

      await user.click(option2)
      expect(mockOnChange).toHaveBeenCalledWith(['option1', 'option2'])
    })

    it('removes value when deselecting checkbox', async () => {
      const user = userEvent.setup()
      render(
        <ChoicesInput
          {...defaultProps}
          config={multipleConfig}
          value={['option1', 'option2']}
        />
      )

      const option1 = getChoiceInput(1)
      await user.click(option1)

      expect(mockOnChange).toHaveBeenCalledWith(['option2'])
    })

    it('calls onAnnotation with array of values', async () => {
      const user = userEvent.setup()
      render(<ChoicesInput {...defaultProps} config={multipleConfig} />)

      const option1 = getChoiceInput(1)
      const option2 = getChoiceInput(2)

      await user.click(option1)
      await user.click(option2)

      expect(mockOnAnnotation).toHaveBeenLastCalledWith({
        from_name: 'category',
        to_name: 'text',
        type: 'Choices',
        value: ['option1', 'option2'],
      })
    })
  })

  describe('Layout Options', () => {
    it('applies vertical layout by default', () => {
      render(<ChoicesInput {...defaultProps} />)

      // The layout container doesn't have a testid, but we can verify by checking
      // that options render in a vertical layout (space-y-2 class is applied to the parent div)
      const option1 = getChoiceInput(1)
      expect(option1.parentElement?.parentElement).toHaveClass('space-y-2')
    })

    it('applies horizontal layout when specified', () => {
      const horizontalConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, layout: 'horizontal' },
      }

      render(<ChoicesInput {...defaultProps} config={horizontalConfig} />)

      const option1 = getChoiceInput(1)
      expect(option1.parentElement?.parentElement).toHaveClass('flex')
      expect(option1.parentElement?.parentElement).toHaveClass('flex-wrap')
      expect(option1.parentElement?.parentElement).toHaveClass('gap-4')
    })
  })

  describe('Pre-selected Values', () => {
    it('initializes with pre-selected choice', () => {
      const configWithSelected = {
        ...defaultConfig,
        children: [
          {
            type: 'Choice',
            props: { value: 'option1', alias: 'Option 1', selected: 'true' },
          },
          {
            type: 'Choice',
            props: { value: 'option2', alias: 'Option 2' },
          },
        ],
      }

      render(<ChoicesInput {...defaultProps} config={configWithSelected} />)

      const option1 = getChoiceInput(1)
      expect(option1).toBeChecked()
    })

    it('calls onChange with pre-selected value on mount', () => {
      const configWithSelected = {
        ...defaultConfig,
        children: [
          {
            type: 'Choice',
            props: { value: 'option1', alias: 'Option 1', selected: 'true' },
          },
        ],
      }

      render(<ChoicesInput {...defaultProps} config={configWithSelected} />)

      expect(mockOnChange).toHaveBeenCalledWith('option1')
    })
  })

  describe('External Value Control', () => {
    it('displays external value when provided', () => {
      render(<ChoicesInput {...defaultProps} value="option2" />)

      const option2 = getChoiceInput(2)
      expect(option2).toBeChecked()
    })

    it('syncs with external value changes', () => {
      const { rerender } = render(
        <ChoicesInput {...defaultProps} value="option1" />
      )

      const option1 = getChoiceInput(1)
      expect(option1).toBeChecked()

      rerender(<ChoicesInput {...defaultProps} value="option2" />)

      const option2 = getChoiceInput(2)
      expect(option2).toBeChecked()
      expect(option1).not.toBeChecked()
    })

    it('handles array values for multiple choice', () => {
      const multipleConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, choice: 'multiple' },
      }

      render(
        <ChoicesInput
          {...defaultProps}
          config={multipleConfig}
          value={['option1', 'option3']}
        />
      )

      const option1 = getChoiceInput(1)
      const option3 = getChoiceInput(3)

      expect(option1).toBeChecked()
      expect(option3).toBeChecked()
    })

    it('converts non-array value to array internally', () => {
      render(<ChoicesInput {...defaultProps} value="option1" />)

      const option1 = getChoiceInput(1)
      expect(option1).toBeChecked()
    })
  })

  describe('Choice Formats', () => {
    it('handles choices with value property', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Choice',
            props: { value: 'val1' },
          },
        ],
      }

      render(<ChoicesInput {...defaultProps} config={config} />)

      expect(screen.getByText('val1')).toBeInTheDocument()
    })

    it('handles choices with alias for display', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Choice',
            props: { value: 'val1', alias: 'Display Name' },
          },
        ],
      }

      render(<ChoicesInput {...defaultProps} config={config} />)

      expect(screen.getByText('Display Name')).toBeInTheDocument()
    })

    it('handles choices with content property', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Choice',
            props: { content: 'Content Text' },
          },
        ],
      }

      render(<ChoicesInput {...defaultProps} config={config} />)

      expect(screen.getByText('Content Text')).toBeInTheDocument()
    })

    it('filters out non-Choice children', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Choice',
            props: { value: 'option1', alias: 'Option 1' },
          },
          {
            type: 'OtherElement',
            props: { value: 'other' },
          },
        ],
      }

      render(<ChoicesInput {...defaultProps} config={config} />)

      expect(screen.getByText('Option 1')).toBeInTheDocument()
      expect(screen.queryByText('other')).not.toBeInTheDocument()
    })
  })

  describe('Required Validation', () => {
    it('marks input as required when no selection and required=true', () => {
      const requiredConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, required: 'true' },
      }

      render(<ChoicesInput {...defaultProps} config={requiredConfig} />)

      const option1 = getChoiceInput(1)
      expect(option1).toBeRequired()
    })

    it('removes required when option is selected', async () => {
      const user = userEvent.setup()
      const requiredConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, required: 'true' },
      }

      render(<ChoicesInput {...defaultProps} config={requiredConfig} />)

      const option1 = getChoiceInput(1)
      await user.click(option1)

      expect(option1).not.toBeRequired()
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

      render(<ChoicesInput {...defaultProps} config={configWithoutToName} />)

      const option1 = getChoiceInput(1)
      await user.click(option1)

      expect(mockOnAnnotation).not.toHaveBeenCalled()
    })

    it('creates annotation with correct structure', async () => {
      const user = userEvent.setup()
      render(<ChoicesInput {...defaultProps} />)

      const option1 = getChoiceInput(1)
      await user.click(option1)

      expect(mockBuildAnnotationResult).toHaveBeenCalledWith(
        'category',
        'Choices',
        'option1',
        'text'
      )
    })
  })

  describe('Edge Cases', () => {
    it('handles empty children array', () => {
      const emptyConfig = {
        ...defaultConfig,
        children: [],
      }

      render(<ChoicesInput {...defaultProps} config={emptyConfig} />)

      // When there are no choices, no radio/checkbox inputs should be rendered
      expect(screen.queryByRole('radio')).not.toBeInTheDocument()
      expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    })

    it('handles undefined external value', () => {
      render(<ChoicesInput {...defaultProps} value={undefined} />)

      const option1 = getChoiceInput(1)
      expect(option1).not.toBeChecked()
    })

    it('handles null external value', () => {
      render(<ChoicesInput {...defaultProps} value={null} />)

      const option1 = getChoiceInput(1)
      expect(option1).not.toBeChecked()
    })

    it('uses fallback name when name not provided', () => {
      const configWithoutName = {
        ...defaultConfig,
        name: undefined,
        props: {
          ...defaultConfig.props,
          name: undefined,
          label: undefined,
        },
      }

      render(<ChoicesInput {...defaultProps} config={configWithoutName} />)

      expect(screen.getByText('choices')).toBeInTheDocument()
    })

    it('handles rapid selection changes', async () => {
      const user = userEvent.setup()
      render(<ChoicesInput {...defaultProps} />)

      const option1 = getChoiceInput(1)
      const option2 = getChoiceInput(2)
      const option3 = getChoiceInput(3)

      await user.click(option1)
      await user.click(option2)
      await user.click(option3)

      expect(option3).toBeChecked()
      expect(mockOnChange).toHaveBeenCalledTimes(3)
    })
  })

  describe('Accessibility', () => {
    it('groups radio buttons with same name', () => {
      render(<ChoicesInput {...defaultProps} />)

      const option1 = getChoiceInput(1)
      const option2 = getChoiceInput(2)

      expect(option1).toHaveAttribute('name', 'category')
      expect(option2).toHaveAttribute('name', 'category')
    })

    it('has clickable labels', async () => {
      const user = userEvent.setup()
      render(<ChoicesInput {...defaultProps} />)

      // The labels don't have test IDs, but clicking on the text label should check the input
      const label = screen.getByText('Option 1')
      await user.click(label)

      const option1 = getChoiceInput(1)
      expect(option1).toBeChecked()
    })
  })
})
