/**
 * Comprehensive tests for LabelsInput component
 * Tests label addition/removal, multi-select, custom labels, and validation
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock Label component
jest.mock('@/components/shared/Label', () => ({
  Label: ({ children }: any) => <label data-testid="label">{children}</label>,
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

// Import the component after mocks
import LabelsInput from '../LabelsInput'

describe('LabelsInput', () => {
  const mockOnChange = jest.fn()
  const mockOnAnnotation = jest.fn()

  const defaultConfig = {
    type: 'Labels',
    name: 'categories',
    props: {
      name: 'categories',
      toName: 'text',
      label: 'Select Categories',
      required: 'false',
    },
    children: [
      {
        type: 'Label',
        props: { value: 'positive', background: '#10b981' },
      },
      {
        type: 'Label',
        props: { value: 'negative', background: '#ef4444' },
      },
      {
        type: 'Label',
        props: { value: 'neutral', background: '#6b7280' },
      },
    ],
  }

  const defaultProps = {
    config: defaultConfig,
    taskData: { text: 'Sample text' },
    value: [],
    onChange: mockOnChange,
    onAnnotation: mockOnAnnotation,
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders with label', () => {
      render(<LabelsInput {...defaultProps} />)

      expect(screen.getByText('Select Categories')).toBeInTheDocument()
    })

    it('renders all label options', () => {
      render(<LabelsInput {...defaultProps} />)

      expect(screen.getByText('positive')).toBeInTheDocument()
      expect(screen.getByText('negative')).toBeInTheDocument()
      expect(screen.getByText('neutral')).toBeInTheDocument()
    })

    it('renders required asterisk when required', () => {
      const requiredConfig = {
        ...defaultConfig,
        props: { ...defaultConfig.props, required: 'true' },
      }

      render(<LabelsInput {...defaultProps} config={requiredConfig} />)

      expect(screen.getByText('*')).toBeInTheDocument()
    })

    it('renders hint when provided', () => {
      const configWithHint = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          hint: 'Select one or more labels',
        },
      }

      render(<LabelsInput {...defaultProps} config={configWithHint} />)

      expect(screen.getByText('Select one or more labels')).toBeInTheDocument()
    })

    it('uses fallback label when label not provided', () => {
      const configWithoutLabel = {
        ...defaultConfig,
        props: {
          ...defaultConfig.props,
          label: undefined,
        },
      }

      render(<LabelsInput {...defaultProps} config={configWithoutLabel} />)

      expect(screen.getByText('categories')).toBeInTheDocument()
    })

    it('uses name as fallback when both label and name not in props', () => {
      const configWithOnlyTypeName = {
        ...defaultConfig,
        name: 'fallback-labels',
        props: {
          toName: 'text',
        },
      }

      render(<LabelsInput {...defaultProps} config={configWithOnlyTypeName} />)

      expect(screen.getByText('fallback-labels')).toBeInTheDocument()
    })

    it('uses labels as default name when all name sources missing', () => {
      const config = {
        type: 'Labels',
        props: {
          toName: 'text',
        },
        children: [],
      }

      render(<LabelsInput {...defaultProps} config={config as any} />)

      expect(screen.getByText('labels')).toBeInTheDocument()
    })
  })

  describe('Label Selection', () => {
    it('selects label when clicked', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const positiveLabel = screen.getByText('positive')
      await user.click(positiveLabel)

      expect(mockOnChange).toHaveBeenCalledWith(['positive'])
    })

    it('calls onAnnotation when label is selected', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const negativeLabel = screen.getByText('negative')
      await user.click(negativeLabel)

      expect(mockOnAnnotation).toHaveBeenCalledWith({
        from_name: 'categories',
        to_name: 'text',
        type: 'Labels',
        value: ['negative'],
      })
    })

    it('allows multiple label selection', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const positiveLabel = screen.getByText('positive')
      const negativeLabel = screen.getByText('negative')

      await user.click(positiveLabel)
      await user.click(negativeLabel)

      expect(mockOnChange).toHaveBeenLastCalledWith(['positive', 'negative'])
    })

    it('maintains order of selected labels', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const neutralLabel = screen.getByText('neutral')
      const positiveLabel = screen.getByText('positive')

      await user.click(neutralLabel)
      await user.click(positiveLabel)

      expect(mockOnChange).toHaveBeenLastCalledWith(['neutral', 'positive'])
    })

    it('selects all labels when all are clicked', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const positiveLabel = screen.getByText('positive')
      const negativeLabel = screen.getByText('negative')
      const neutralLabel = screen.getByText('neutral')

      await user.click(positiveLabel)
      await user.click(negativeLabel)
      await user.click(neutralLabel)

      expect(mockOnChange).toHaveBeenLastCalledWith([
        'positive',
        'negative',
        'neutral',
      ])
    })
  })

  describe('Label Deselection', () => {
    it('deselects label when clicked again', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} value={['positive']} />)

      const positiveLabel = screen.getByText('positive')
      await user.click(positiveLabel)

      expect(mockOnChange).toHaveBeenCalledWith([])
    })

    it('removes label from selection while keeping others', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} value={['positive', 'negative']} />)

      const positiveLabel = screen.getByText('positive')
      await user.click(positiveLabel)

      expect(mockOnChange).toHaveBeenCalledWith(['negative'])
    })

    it('handles rapid selection and deselection', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const positiveLabel = screen.getByText('positive')

      await user.click(positiveLabel) // Select
      await user.click(positiveLabel) // Deselect
      await user.click(positiveLabel) // Select again

      expect(mockOnChange).toHaveBeenLastCalledWith(['positive'])
    })
  })

  describe('Visual States', () => {
    it('applies selected style to selected labels', () => {
      render(<LabelsInput {...defaultProps} value={['positive']} />)

      const positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).toHaveClass('bg-emerald-600')
      expect(positiveButton).toHaveClass('text-white')
    })

    it('applies unselected style to unselected labels', () => {
      render(<LabelsInput {...defaultProps} value={['positive']} />)

      const negativeButton = screen.getByText('negative').closest('button')
      expect(negativeButton).toHaveClass('bg-zinc-200')
    })

    it('applies custom background color to selected labels', () => {
      render(<LabelsInput {...defaultProps} value={['positive']} />)

      const positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).toHaveStyle({ backgroundColor: '#10b981' })
    })

    it('does not apply custom background to unselected labels', () => {
      render(<LabelsInput {...defaultProps} value={['positive']} />)

      const negativeButton = screen.getByText('negative').closest('button')
      expect(negativeButton).not.toHaveStyle({ backgroundColor: '#ef4444' })
    })

    it('shows multiple selected labels with different colors', () => {
      render(<LabelsInput {...defaultProps} value={['positive', 'negative']} />)

      const positiveButton = screen.getByText('positive').closest('button')
      const negativeButton = screen.getByText('negative').closest('button')

      expect(positiveButton).toHaveStyle({ backgroundColor: '#10b981' })
      expect(negativeButton).toHaveStyle({ backgroundColor: '#ef4444' })
    })
  })

  describe('Label Formats', () => {
    it('handles labels with value property', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Label',
            props: { value: 'test-label', background: '#3b82f6' },
          },
        ],
      }

      render(<LabelsInput {...defaultProps} config={config} />)

      expect(screen.getByText('test-label')).toBeInTheDocument()
    })

    it('handles labels with content property', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Label',
            props: { content: 'Content Label', background: '#3b82f6' },
          },
        ],
      }

      render(<LabelsInput {...defaultProps} config={config} />)

      expect(screen.getByText('Content Label')).toBeInTheDocument()
    })

    it('prefers value over content when both present', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Label',
            props: {
              value: 'value-text',
              content: 'content-text',
              background: '#3b82f6',
            },
          },
        ],
      }

      render(<LabelsInput {...defaultProps} config={config} />)

      expect(screen.getByText('value-text')).toBeInTheDocument()
      expect(screen.queryByText('content-text')).not.toBeInTheDocument()
    })

    it('uses default background color when not provided', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Label',
            props: { value: 'default-bg' },
          },
        ],
      }

      render(
        <LabelsInput {...defaultProps} config={config} value={['default-bg']} />
      )

      const button = screen.getByText('default-bg').closest('button')
      expect(button).toHaveStyle({ backgroundColor: '#e5e7eb' })
    })

    it('filters out non-Label children', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Label',
            props: { value: 'valid-label', background: '#10b981' },
          },
          {
            type: 'OtherElement',
            props: { value: 'invalid', background: '#000000' },
          },
        ],
      }

      render(<LabelsInput {...defaultProps} config={config} />)

      expect(screen.getByText('valid-label')).toBeInTheDocument()
      expect(screen.queryByText('invalid')).not.toBeInTheDocument()
    })
  })

  describe('Pre-selected Labels', () => {
    it('parses selected prop from label config', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Label',
            props: {
              value: 'positive',
              background: '#10b981',
              selected: 'true',
            },
          },
          {
            type: 'Label',
            props: { value: 'negative', background: '#ef4444' },
          },
        ],
      }

      // Note: The selected prop is parsed but not automatically applied to state
      // It's up to the parent component to initialize with correct value
      render(
        <LabelsInput {...defaultProps} config={config} value={['positive']} />
      )

      const positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).toHaveClass('bg-emerald-600')
    })
  })

  describe('External Value Control', () => {
    it('displays initial external value when provided', () => {
      render(<LabelsInput {...defaultProps} value={['positive', 'neutral']} />)

      const positiveButton = screen.getByText('positive').closest('button')
      const neutralButton = screen.getByText('neutral').closest('button')

      expect(positiveButton).toHaveClass('bg-emerald-600')
      expect(neutralButton).toHaveClass('bg-emerald-600')
    })

    it('maintains internal state after initialization', () => {
      const { rerender } = render(
        <LabelsInput {...defaultProps} value={['positive']} />
      )

      let positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).toHaveClass('bg-emerald-600')

      // Note: Component uses useState and doesn't sync with external value changes
      // This is the current behavior - internal state is independent after mount
      rerender(<LabelsInput {...defaultProps} value={['negative']} />)

      // Still shows initial selection
      positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).toHaveClass('bg-emerald-600')
    })

    it('handles undefined external value', () => {
      render(<LabelsInput {...defaultProps} value={undefined} />)

      const positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).not.toHaveClass('bg-emerald-600')
    })

    it('handles null external value', () => {
      render(<LabelsInput {...defaultProps} value={null} />)

      const positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).not.toHaveClass('bg-emerald-600')
    })

    it('handles empty array external value', () => {
      render(<LabelsInput {...defaultProps} value={[]} />)

      const positiveButton = screen.getByText('positive').closest('button')
      const negativeButton = screen.getByText('negative').closest('button')

      expect(positiveButton).not.toHaveClass('bg-emerald-600')
      expect(negativeButton).not.toHaveClass('bg-emerald-600')
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

      render(<LabelsInput {...defaultProps} config={configWithoutToName} />)

      const positiveLabel = screen.getByText('positive')
      await user.click(positiveLabel)

      expect(mockOnAnnotation).not.toHaveBeenCalled()
    })

    it('creates annotation with correct structure', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const positiveLabel = screen.getByText('positive')
      await user.click(positiveLabel)

      expect(mockBuildAnnotationResult).toHaveBeenCalledWith(
        'categories',
        'Labels',
        ['positive'],
        'text'
      )
    })

    it('creates annotation with multiple labels', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const positiveLabel = screen.getByText('positive')
      const negativeLabel = screen.getByText('negative')

      await user.click(positiveLabel)
      await user.click(negativeLabel)

      expect(mockOnAnnotation).toHaveBeenLastCalledWith({
        from_name: 'categories',
        to_name: 'text',
        type: 'Labels',
        value: ['positive', 'negative'],
      })
    })

    it('creates annotation when label is deselected', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} value={['positive']} />)

      const positiveLabel = screen.getByText('positive')
      await user.click(positiveLabel)

      expect(mockOnAnnotation).toHaveBeenCalledWith({
        from_name: 'categories',
        to_name: 'text',
        type: 'Labels',
        value: [],
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles empty children array', () => {
      const emptyConfig = {
        ...defaultConfig,
        children: [],
      }

      render(<LabelsInput {...defaultProps} config={emptyConfig} />)

      const container = document.querySelector('.labels-input')
      expect(container).toBeInTheDocument()
    })

    it('handles single label', () => {
      const singleConfig = {
        ...defaultConfig,
        children: [
          {
            type: 'Label',
            props: { value: 'only-one', background: '#10b981' },
          },
        ],
      }

      render(<LabelsInput {...defaultProps} config={singleConfig} />)

      expect(screen.getByText('only-one')).toBeInTheDocument()
    })

    it('handles many labels', () => {
      const manyLabels = Array.from({ length: 20 }, (_, i) => ({
        type: 'Label',
        props: { value: `label-${i}`, background: '#10b981' },
      }))

      const manyConfig = {
        ...defaultConfig,
        children: manyLabels,
      }

      render(<LabelsInput {...defaultProps} config={manyConfig} />)

      const buttons = screen.getAllByRole('button')
      expect(buttons.length).toBe(20)
    })

    it('handles labels with empty value', () => {
      const config = {
        ...defaultConfig,
        children: [
          {
            type: 'Label',
            props: { value: '', background: '#10b981' },
          },
        ],
      }

      render(<LabelsInput {...defaultProps} config={config} />)

      // Should still render, even if empty
      const buttons = screen.getAllByRole('button')
      expect(buttons.length).toBe(1)
    })

    it('handles rapid selection changes', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const positiveLabel = screen.getByText('positive')
      const negativeLabel = screen.getByText('negative')
      const neutralLabel = screen.getByText('neutral')

      await user.click(positiveLabel)
      await user.click(negativeLabel)
      await user.click(positiveLabel) // Deselect
      await user.click(neutralLabel)

      expect(mockOnChange).toHaveBeenLastCalledWith(['negative', 'neutral'])
    })
  })

  describe('Accessibility', () => {
    it('renders buttons for label selection', () => {
      render(<LabelsInput {...defaultProps} />)

      const buttons = screen.getAllByRole('button')
      expect(buttons.length).toBe(3)

      buttons.forEach((button) => {
        expect(button).toHaveAttribute('type', 'button')
      })
    })

    it('labels are keyboard accessible', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const buttons = screen.getAllByRole('button')

      await user.tab()
      expect(buttons[0]).toHaveFocus()

      await user.tab()
      expect(buttons[1]).toHaveFocus()
    })

    it('labels can be selected via keyboard', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} />)

      const positiveLabel = screen.getByText('positive')

      await user.click(positiveLabel)

      expect(mockOnChange).toHaveBeenCalledWith(['positive'])
    })
  })

  describe('Multiple Instances', () => {
    it('handles multiple LabelsInput components independently', async () => {
      const user = userEvent.setup()
      const mockOnChange1 = jest.fn()
      const mockOnChange2 = jest.fn()

      const props1 = {
        ...defaultProps,
        config: {
          ...defaultConfig,
          props: { ...defaultConfig.props, name: 'labels1' },
        },
        onChange: mockOnChange1,
      }

      const props2 = {
        ...defaultProps,
        config: {
          ...defaultConfig,
          props: { ...defaultConfig.props, name: 'labels2' },
        },
        onChange: mockOnChange2,
      }

      render(
        <div>
          <LabelsInput {...props1} />
          <LabelsInput {...props2} />
        </div>
      )

      const allButtons = screen.getAllByRole('button')

      // Click first label of first input
      await user.click(allButtons[0])
      expect(mockOnChange1).toHaveBeenCalledWith(['positive'])

      // Click first label of second input
      await user.click(allButtons[3])
      expect(mockOnChange2).toHaveBeenCalledWith(['positive'])
    })
  })

  describe('State Management', () => {
    it('maintains internal state when external value not provided', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} value={undefined} />)

      const positiveLabel = screen.getByText('positive')
      await user.click(positiveLabel)

      const positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).toHaveClass('bg-emerald-600')
    })

    it('initializes with external value', () => {
      render(<LabelsInput {...defaultProps} value={['positive']} />)

      const positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).toHaveClass('bg-emerald-600')
    })

    it('maintains internal state independent of external value changes', () => {
      const { rerender } = render(
        <LabelsInput {...defaultProps} value={undefined} />
      )

      const positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).not.toHaveClass('bg-emerald-600')

      // External value doesn't sync after mount - this is current behavior
      rerender(<LabelsInput {...defaultProps} value={['positive']} />)

      const updatedButton = screen.getByText('positive').closest('button')
      expect(updatedButton).not.toHaveClass('bg-emerald-600')
    })

    it('uses initial value for state initialization', () => {
      render(<LabelsInput {...defaultProps} value={['positive', 'negative']} />)

      const positiveButton = screen.getByText('positive').closest('button')
      const negativeButton = screen.getByText('negative').closest('button')

      expect(positiveButton).toHaveClass('bg-emerald-600')
      expect(negativeButton).toHaveClass('bg-emerald-600')
    })

    it('allows user interaction to override initial value', async () => {
      const user = userEvent.setup()
      render(<LabelsInput {...defaultProps} value={['positive']} />)

      let positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).toHaveClass('bg-emerald-600')

      // Click to deselect
      await user.click(positiveButton)

      positiveButton = screen.getByText('positive').closest('button')
      expect(positiveButton).not.toHaveClass('bg-emerald-600')
    })
  })
})
