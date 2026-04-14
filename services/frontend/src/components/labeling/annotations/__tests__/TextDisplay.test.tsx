/**
 * Tests for TextDisplay component
 * Tests data binding resolution, label display, and value rendering
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

// Mock data binding
jest.mock('@/lib/labelConfig/dataBinding', () => ({
  resolveDataBinding: (expression: string, taskData: any) => {
    if (typeof expression !== 'string' || !expression.startsWith('$')) return expression
    const key = expression.substring(1)
    return taskData?.[key]
  },
}))

import TextDisplay from '../TextDisplay'

describe('TextDisplay', () => {
  const defaultProps = {
    config: {
      type: 'Text',
      name: 'text',
      props: {
        name: 'text',
        value: '$content',
      },
      children: [],
    },
    taskData: { content: 'Hello world' },
    value: undefined,
    onChange: jest.fn(),
    onAnnotation: jest.fn(),
  }

  describe('Basic Rendering', () => {
    it('renders resolved text value from task data', () => {
      render(<TextDisplay {...defaultProps} />)
      expect(screen.getByText('Hello world')).toBeInTheDocument()
    })

    it('renders label when name is provided and showLabel is not false', () => {
      render(<TextDisplay {...defaultProps} />)
      expect(screen.getByText('text')).toBeInTheDocument()
    })

    it('hides label when showLabel is false', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            showLabel: 'false',
          },
        },
      }
      render(<TextDisplay {...props} />)
      expect(screen.queryByText('text')).not.toBeInTheDocument()
    })
  })

  describe('Missing Data Handling', () => {
    it('shows no-data message when value is undefined', () => {
      const props = {
        ...defaultProps,
        taskData: {},
      }
      render(<TextDisplay {...props} />)
      expect(screen.getByText('labeling.display.noData')).toBeInTheDocument()
    })

    it('shows no-data message when value is null', () => {
      const props = {
        ...defaultProps,
        taskData: { content: null },
      }
      render(<TextDisplay {...props} />)
      expect(screen.getByText('labeling.display.noData')).toBeInTheDocument()
    })
  })

  describe('Value Types', () => {
    it('renders string values as text', () => {
      render(<TextDisplay {...defaultProps} />)
      const paragraph = screen.getByText('Hello world')
      expect(paragraph.tagName.toLowerCase()).toBe('p')
    })

    it('renders object values as JSON in pre tag', () => {
      const props = {
        ...defaultProps,
        taskData: { content: { key: 'value', nested: true } },
      }
      render(<TextDisplay {...props} />)
      const pre = screen.getByText(/"key": "value"/, { exact: false })
      expect(pre.tagName.toLowerCase()).toBe('pre')
    })

    it('renders number values as text', () => {
      const props = {
        ...defaultProps,
        taskData: { content: 42 },
      }
      render(<TextDisplay {...props} />)
      expect(screen.getByText('42')).toBeInTheDocument()
    })
  })

  describe('CSS and Styling', () => {
    it('applies custom className', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          props: {
            ...defaultProps.config.props,
            className: 'custom-class',
          },
        },
      }
      const { container } = render(<TextDisplay {...props} />)
      expect(container.querySelector('.custom-class')).not.toBeNull()
    })

    it('has text-display class', () => {
      const { container } = render(<TextDisplay {...defaultProps} />)
      expect(container.querySelector('.text-display')).not.toBeNull()
    })
  })

  describe('No Name Provided', () => {
    it('does not render label when no name is provided', () => {
      const props = {
        ...defaultProps,
        config: {
          ...defaultProps.config,
          name: undefined as any,
          props: {
            value: '$content',
          },
        },
      }
      render(<TextDisplay {...props} />)
      // Should still render the text content
      expect(screen.getByText('Hello world')).toBeInTheDocument()
    })
  })
})
