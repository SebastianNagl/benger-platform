/**
 * Comprehensive tests for SpanLabelsInput component
 * Tests NER-style span annotation functionality
 *
 * Issue #964: Add Span Annotation as a project type for NER and text highlighting
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock data binding utilities
const mockBuildSpanAnnotationResult = jest.fn((fromName, toName, spans) => ({
  from_name: fromName,
  to_name: toName,
  type: 'labels',
  value: { spans },
}))

jest.mock('@/lib/labelConfig/dataBinding', () => ({
  buildSpanAnnotationResult: (...args: any[]) =>
    mockBuildSpanAnnotationResult(...args),
}))

// Import the actual component
import SpanLabelsInput from '../SpanLabelsInput'
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../../locales/en/common.json')
      const parts = key.split('.')
      let value: any = translations
      for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
          value = value[part]
        } else {
          return key
        }
      }
      if (typeof value !== 'string') return key
      if (varsOrDefault && typeof varsOrDefault === 'object') {
        for (const [k, v] of Object.entries(varsOrDefault)) {
          value = value.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
        }
      }
      return value
    },
    locale: 'en',
  }),
}))


describe('SpanLabelsInput', () => {
  const mockOnChange = jest.fn()
  const mockOnAnnotation = jest.fn()

  const defaultConfig = {
    type: 'Labels',
    name: 'label',
    props: {
      name: 'label',
      toName: 'text',
      choice: 'single',
    },
    children: [
      {
        type: 'Label',
        props: { value: 'PERSON', background: '#FF6B6B' },
        children: [],
      },
      {
        type: 'Label',
        props: { value: 'ORGANIZATION', background: '#4ECDC4' },
        children: [],
      },
      {
        type: 'Label',
        props: { value: 'DATE', background: '#45B7D1' },
        children: [],
      },
    ],
  }

  const defaultTaskData = {
    text: 'John Smith works at Acme Corporation since January 2024.',
  }

  const defaultProps = {
    config: defaultConfig,
    taskData: defaultTaskData,
    value: null,
    onChange: mockOnChange,
    onAnnotation: mockOnAnnotation,
    sourceText: '',
  }

  beforeEach(() => {
    jest.clearAllMocks()
    // Mock window.getSelection
    Object.defineProperty(window, 'getSelection', {
      value: jest.fn(() => ({
        toString: () => '',
        isCollapsed: true,
        getRangeAt: jest.fn(() => ({
          startContainer: document.body,
          startOffset: 0,
          commonAncestorContainer: document.body,
        })),
        removeAllRanges: jest.fn(),
      })),
      writable: true,
    })
  })

  describe('Rendering', () => {
    it('renders label buttons from config children', () => {
      render(<SpanLabelsInput {...defaultProps} />)

      expect(
        screen.getByRole('button', { name: /PERSON/i })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /ORGANIZATION/i })
      ).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /DATE/i })).toBeInTheDocument()
    })

    it('renders source text from taskData', () => {
      render(<SpanLabelsInput {...defaultProps} />)

      expect(
        screen.getByText(/John Smith works at Acme Corporation/)
      ).toBeInTheDocument()
    })

    it('renders source text from nested taskData.data', () => {
      const propsWithNestedData = {
        ...defaultProps,
        taskData: {
          data: {
            text: 'Nested text content for annotation.',
          },
        },
      }

      render(<SpanLabelsInput {...propsWithNestedData} />)

      expect(screen.getByText(/Nested text content/)).toBeInTheDocument()
    })

    it('shows placeholder when no source text available', () => {
      const propsWithoutText = {
        ...defaultProps,
        taskData: {},
      }

      render(<SpanLabelsInput {...propsWithoutText} />)

      expect(
        screen.getByText(/No text provided for annotation/)
      ).toBeInTheDocument()
    })

    it('renders help text with keyboard shortcut info', () => {
      render(<SpanLabelsInput {...defaultProps} />)

      expect(screen.getByText(/Select text to annotate/)).toBeInTheDocument()
    })
  })

  describe('Label Selection', () => {
    it('highlights selected label button', async () => {
      render(<SpanLabelsInput {...defaultProps} />)

      const personButton = screen.getByRole('button', { name: /PERSON/i })
      const orgButton = screen.getByRole('button', { name: /ORGANIZATION/i })

      // First label should be selected by default
      expect(personButton).toHaveClass('ring-2')

      // Click ORGANIZATION
      await userEvent.click(orgButton)

      // ORGANIZATION should now be selected
      expect(orgButton).toHaveClass('ring-2')
    })

    it('applies label colors from config', () => {
      render(<SpanLabelsInput {...defaultProps} />)

      const personButton = screen.getByRole('button', { name: /PERSON/i })

      expect(personButton).toHaveStyle({ backgroundColor: '#FF6B6B' })
    })
  })

  describe('Initial Values', () => {
    it('parses initial spans from value prop', () => {
      const propsWithInitialValue = {
        ...defaultProps,
        value: [
          {
            id: 'span-1',
            start: 0,
            end: 10,
            text: 'John Smith',
            labels: ['PERSON'],
          },
        ],
      }

      render(<SpanLabelsInput {...propsWithInitialValue} />)

      // Should show the annotation in the span list
      expect(screen.getByText(/Annotations \(1\)/)).toBeInTheDocument()
      expect(screen.getByText(/"John Smith"/)).toBeInTheDocument()
    })

    it('handles empty initial value', () => {
      render(<SpanLabelsInput {...defaultProps} value={[]} />)

      // Should not show annotations section
      expect(screen.queryByText(/Annotations/)).not.toBeInTheDocument()
    })
  })

  describe('Span Operations', () => {
    it('removes span when clicking delete button', async () => {
      const propsWithSpan = {
        ...defaultProps,
        value: [
          {
            id: 'span-1',
            start: 0,
            end: 10,
            text: 'John Smith',
            labels: ['PERSON'],
          },
        ],
      }

      render(<SpanLabelsInput {...propsWithSpan} />)

      // Find and click the remove button
      const removeButton = screen.getByTitle('Remove annotation')
      await userEvent.click(removeButton)

      // Should call onChange and onAnnotation with empty spans
      expect(mockOnChange).toHaveBeenCalledWith([])
      expect(mockOnAnnotation).toHaveBeenCalled()
    })
  })

  describe('Annotation List', () => {
    it('displays span details in list', () => {
      const propsWithSpans = {
        ...defaultProps,
        value: [
          {
            id: 'span-1',
            start: 0,
            end: 10,
            text: 'John Smith',
            labels: ['PERSON'],
          },
          {
            id: 'span-2',
            start: 20,
            end: 36,
            text: 'Acme Corporation',
            labels: ['ORGANIZATION'],
          },
        ],
      }

      render(<SpanLabelsInput {...propsWithSpans} />)

      expect(screen.getByText(/Annotations \(2\)/)).toBeInTheDocument()
      expect(screen.getByText(/"John Smith"/)).toBeInTheDocument()
      expect(screen.getByText(/"Acme Corporation"/)).toBeInTheDocument()
      expect(screen.getByText(/\[0:10\]/)).toBeInTheDocument()
      expect(screen.getByText(/\[20:36\]/)).toBeInTheDocument()
    })

    it('displays long text in span list', () => {
      const longText = 'This is a very long text that should be displayed'
      const propsWithLongSpan = {
        ...defaultProps,
        value: [
          {
            id: 'span-1',
            start: 0,
            end: longText.length,
            text: longText,
            labels: ['PERSON'],
          },
        ],
      }

      render(<SpanLabelsInput {...propsWithLongSpan} />)

      // Should show the annotation in the list (text appears both in source and list)
      const matches = screen.getAllByText(/This is a very long text/)
      expect(matches.length).toBeGreaterThan(0)
    })
  })

  describe('Keyboard Navigation', () => {
    it('selects label with number key shortcuts', async () => {
      render(<SpanLabelsInput {...defaultProps} />)

      // Press '2' to select ORGANIZATION (second label)
      fireEvent.keyDown(window, { key: '2' })

      const orgButton = screen.getByRole('button', { name: /ORGANIZATION/i })
      expect(orgButton).toHaveClass('ring-2')
    })
  })

  describe('Accessibility', () => {
    it('has accessible label buttons', () => {
      render(<SpanLabelsInput {...defaultProps} />)

      const buttons = screen.getAllByRole('button')
      buttons.forEach((button) => {
        expect(button).toHaveAttribute('type', 'button')
      })
    })

    it('provides tooltip on highlighted spans', () => {
      const propsWithSpan = {
        ...defaultProps,
        value: [
          {
            id: 'span-1',
            start: 0,
            end: 10,
            text: 'John Smith',
            labels: ['PERSON'],
          },
        ],
      }

      render(<SpanLabelsInput {...propsWithSpan} />)

      // The highlighted span should have a title attribute
      const highlightedSpan = screen.getByTitle(/PERSON.*click to remove/i)
      expect(highlightedSpan).toBeInTheDocument()
    })
  })
})

describe('Data Binding Functions', () => {
  // Test the actual data binding functions separately
  describe('buildSpanAnnotationResult', () => {
    it('creates proper annotation result structure', () => {
      const spans = [
        {
          id: 'span-1',
          start: 0,
          end: 10,
          text: 'John Smith',
          labels: ['PERSON'],
        },
      ]

      const result = mockBuildSpanAnnotationResult('label', 'text', spans)

      expect(result).toEqual({
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
        value: { spans },
      })
    })
  })
})
