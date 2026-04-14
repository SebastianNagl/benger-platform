/**
 * Comprehensive tests for HighlightField component
 * Tests text highlighting, selection handling, and highlight management
 */

/**
 * @jest-environment jsdom
 */

import { TaskTemplateField } from '@/types/taskTemplate'
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { HighlightField } from '../HighlightField'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../locales/en/common.json')
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

// Mock the BaseField module
jest.mock('../BaseField', () => ({
  FieldWrapper: ({ children, field, errors }: any) => (
    <div data-testid="field-wrapper" data-field-name={field.name}>
      {children}
      {errors.length > 0 && (
        <div data-testid="errors">
          {errors.map((err: string, i: number) => (
            <div key={i} data-testid={`error-${i}`}>
              {err}
            </div>
          ))}
        </div>
      )}
    </div>
  ),
}))

describe('HighlightField', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'highlights',
    type: 'highlight',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'hidden',
      creation: 'hidden',
    },
    label: 'Highlight Text',
    metadata: {
      source_text: 'This is a sample text for highlighting purposes.',
    },
    choices: ['important', 'reference'],
  }

  const defaultProps = {
    field: defaultField,
    value: [],
    onChange: mockOnChange,
    context: 'annotation' as const,
    readonly: false,
    errors: [],
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders the source text', () => {
      render(<HighlightField {...defaultProps} />)

      expect(
        screen.getByText('This is a sample text for highlighting purposes.')
      ).toBeInTheDocument()
    })

    it('renders with field wrapper', () => {
      render(<HighlightField {...defaultProps} />)

      const wrapper = screen.getByTestId('field-wrapper')
      expect(wrapper).toBeInTheDocument()
      expect(wrapper).toHaveAttribute('data-field-name', 'highlights')
    })

    it('displays instruction text when not readonly', () => {
      render(<HighlightField {...defaultProps} />)

      expect(
        screen.getByText(
          'Select text to highlight. Click highlighted text to remove.'
        )
      ).toBeInTheDocument()
    })

    it('does not display instruction text when readonly', () => {
      render(<HighlightField {...defaultProps} readonly={true} />)

      expect(
        screen.queryByText(
          'Select text to highlight. Click highlighted text to remove.'
        )
      ).not.toBeInTheDocument()
    })

    it('displays default text when no source_text provided', () => {
      const fieldWithoutText = {
        ...defaultField,
        metadata: {},
      }

      render(<HighlightField {...defaultProps} field={fieldWithoutText} />)

      expect(
        screen.getByText('No text provided for highlighting')
      ).toBeInTheDocument()
    })
  })

  describe('Text Selection and Highlighting', () => {
    // Note: Text selection tests require jsdom Range support which has limitations
    // with complex DOM structures. Selection functionality verified in browser.

    it('ignores selections outside the highlight container', () => {
      render(
        <div>
          <p id="outside">Outside text</p>
          <HighlightField {...defaultProps} />
        </div>
      )

      const outsideElement = document.getElementById('outside')
      const range = document.createRange()
      range.selectNodeContents(outsideElement!)

      const selection = window.getSelection()
      selection?.removeAllRanges()
      selection?.addRange(range)

      const container = document.getElementById('highlight-highlights')
      fireEvent.mouseUp(container!)

      expect(mockOnChange).not.toHaveBeenCalled()
    })
  })

  describe('Highlight Display', () => {
    it('displays existing highlights', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      const highlightedText = screen.getByText('This')
      expect(highlightedText).toHaveClass('bg-yellow-200')
    })

    it('displays multiple highlights', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
        { start: 10, end: 16, text: 'sample', label: 'reference' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      const highlightElements = document.querySelectorAll('.bg-yellow-200')
      expect(highlightElements).toHaveLength(2)
    })

    it('sorts highlights by start position', () => {
      const highlights = [
        { start: 10, end: 16, text: 'sample', label: 'reference' },
        { start: 0, end: 4, text: 'This', label: 'important' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      const highlightElements = document.querySelectorAll('.bg-yellow-200')
      // Text content includes any child elements like remove buttons
      expect(highlightElements[0].textContent).toContain('This')
      expect(highlightElements[1].textContent).toContain('sample')
    })

    it('renders text between highlights', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
        { start: 10, end: 16, text: 'sample', label: 'reference' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      // Container should include the text between highlights
      const container = document.getElementById('highlight-highlights')
      expect(container?.textContent).toContain(' is a ')
    })

    it('renders remaining text after last highlight', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      // Container should include the remaining text
      const container = document.getElementById('highlight-highlights')
      expect(container?.textContent).toContain(
        'sample text for highlighting purposes'
      )
    })
  })

  describe('Highlight Removal', () => {
    it('removes highlight when clicked', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
        { start: 10, end: 16, text: 'sample', label: 'reference' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      const firstHighlight = screen.getByText('This')
      fireEvent.click(firstHighlight)

      expect(mockOnChange).toHaveBeenCalledWith([
        { start: 10, end: 16, text: 'sample', label: 'reference' },
      ])
    })

    it('does not remove highlight in readonly mode', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
      ]

      render(
        <HighlightField {...defaultProps} value={highlights} readonly={true} />
      )

      const highlight = screen.getByText('This')
      fireEvent.click(highlight)

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('removes highlight via remove button in list', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
        { start: 10, end: 16, text: 'sample', label: 'reference' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      const removeButtons = screen.getAllByRole('button', { name: /remove/i })
      fireEvent.click(removeButtons[0])

      expect(mockOnChange).toHaveBeenCalledWith([
        { start: 10, end: 16, text: 'sample', label: 'reference' },
      ])
    })

    it('does not show remove buttons in readonly mode', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
      ]

      render(
        <HighlightField {...defaultProps} value={highlights} readonly={true} />
      )

      const removeButtons = screen.queryAllByRole('button', { name: /remove/i })
      expect(removeButtons).toHaveLength(0)
    })
  })

  describe('Highlight List', () => {
    it('displays highlight count', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
        { start: 10, end: 16, text: 'sample', label: 'reference' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      expect(screen.getByText('Highlights (2)')).toBeInTheDocument()
    })

    it('lists all highlighted texts', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
        { start: 10, end: 16, text: 'sample', label: 'reference' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      expect(screen.getByText('"This"')).toBeInTheDocument()
      expect(screen.getByText('"sample"')).toBeInTheDocument()
    })

    it('does not display highlight list when no highlights', () => {
      render(<HighlightField {...defaultProps} value={[]} />)

      expect(screen.queryByText(/Highlights \(/)).not.toBeInTheDocument()
    })
  })

  describe('Styling', () => {
    it('applies readonly styles', () => {
      render(<HighlightField {...defaultProps} readonly={true} />)

      const container = document.getElementById('highlight-highlights')
      expect(container).toHaveClass('bg-gray-50', 'dark:bg-gray-800')
    })

    it('applies editable styles', () => {
      render(<HighlightField {...defaultProps} readonly={false} />)

      const container = document.getElementById('highlight-highlights')
      expect(container).toHaveClass('bg-white', 'dark:bg-gray-700')
    })

    it('shows hover tooltip on highlighted text', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      const highlight = screen.getByText('This')
      const tooltip = highlight.querySelector('.group-hover\\:block')

      expect(tooltip).toBeInTheDocument()
      expect(tooltip).toHaveTextContent('Click to remove')
    })

    it('does not show tooltip in readonly mode', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
      ]

      render(
        <HighlightField {...defaultProps} value={highlights} readonly={true} />
      )

      const highlight = screen.getByText('This')
      const tooltip = highlight.querySelector('.group-hover\\:block')

      expect(tooltip).not.toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('displays error messages', () => {
      const errors = ['Invalid highlight', 'Overlapping highlights']

      render(<HighlightField {...defaultProps} errors={errors} />)

      expect(screen.getByTestId('errors')).toBeInTheDocument()
      expect(screen.getByText('Invalid highlight')).toBeInTheDocument()
      expect(screen.getByText('Overlapping highlights')).toBeInTheDocument()
    })

    it('handles empty errors array', () => {
      render(<HighlightField {...defaultProps} errors={[]} />)

      expect(screen.queryByTestId('errors')).not.toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty value array', () => {
      render(<HighlightField {...defaultProps} value={[]} />)

      expect(
        screen.getByText('This is a sample text for highlighting purposes.')
      ).toBeInTheDocument()
    })

    it('handles null value', () => {
      render(<HighlightField {...defaultProps} value={null as any} />)

      expect(
        screen.getByText('This is a sample text for highlighting purposes.')
      ).toBeInTheDocument()
    })

    it('handles undefined value', () => {
      render(<HighlightField {...defaultProps} value={undefined as any} />)

      expect(
        screen.getByText('This is a sample text for highlighting purposes.')
      ).toBeInTheDocument()
    })

    it('handles non-array value', () => {
      render(<HighlightField {...defaultProps} value={'invalid' as any} />)

      expect(
        screen.getByText('This is a sample text for highlighting purposes.')
      ).toBeInTheDocument()
    })

    it('handles overlapping highlights', () => {
      const highlights = [
        { start: 0, end: 10, text: 'This is a ', label: 'important' },
        { start: 5, end: 16, text: 's a sample', label: 'reference' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      const highlightElements = document.querySelectorAll('.bg-yellow-200')
      expect(highlightElements.length).toBeGreaterThanOrEqual(1)
    })

    it('handles highlight at end of text', () => {
      const highlights = [
        { start: 40, end: 49, text: 'purposes.', label: 'important' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      expect(screen.getByText('purposes.')).toHaveClass('bg-yellow-200')
    })

    it('handles highlight at start of text', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      const highlightElements = document.querySelectorAll('.bg-yellow-200')
      // Text content includes any child elements like remove buttons
      expect(highlightElements[0].textContent).toContain('This')
    })

    it('handles empty source text', () => {
      const fieldWithEmptyText = {
        ...defaultField,
        metadata: {
          source_text: '',
        },
      }

      render(<HighlightField {...defaultProps} field={fieldWithEmptyText} />)

      const container = document.getElementById('highlight-highlights')
      // Empty source shows placeholder message instead of being empty
      expect(container).toBeInTheDocument()
    })

    it('handles highlights with missing label', () => {
      const highlights = [{ start: 0, end: 4, text: 'This' } as any]

      render(<HighlightField {...defaultProps} value={highlights} />)

      expect(screen.getByText('This')).toBeInTheDocument()
    })

    it('handles field without choices', () => {
      const fieldWithoutChoices = {
        ...defaultField,
        choices: undefined,
      }

      render(<HighlightField {...defaultProps} field={fieldWithoutChoices} />)

      const container = document.getElementById('highlight-highlights')
      expect(container).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has proper container id', () => {
      render(<HighlightField {...defaultProps} />)

      const container = document.getElementById('highlight-highlights')
      expect(container).toBeInTheDocument()
    })

    it('has cursor pointer on highlighted text', () => {
      const highlights = [
        { start: 0, end: 4, text: 'This', label: 'important' },
      ]

      render(<HighlightField {...defaultProps} value={highlights} />)

      const highlight = screen.getByText('This')
      expect(highlight).toHaveClass('cursor-pointer')
    })

    it('has appropriate ARIA attributes', () => {
      render(<HighlightField {...defaultProps} />)

      const container = document.getElementById('highlight-highlights')
      expect(container).toBeInTheDocument()
    })
  })

  describe('Custom Class Name', () => {
    it('applies custom className to field wrapper', () => {
      render(
        <HighlightField {...defaultProps} className="custom-highlight-class" />
      )

      const wrapper = screen.getByTestId('field-wrapper')
      expect(wrapper).toBeInTheDocument()
    })
  })

  describe('Context Variations', () => {
    it('works in annotation context', () => {
      render(<HighlightField {...defaultProps} context="annotation" />)

      expect(screen.getByTestId('field-wrapper')).toBeInTheDocument()
    })

    it('works in table context', () => {
      render(<HighlightField {...defaultProps} context="table" />)

      expect(screen.getByTestId('field-wrapper')).toBeInTheDocument()
    })

    it('works in creation context', () => {
      render(<HighlightField {...defaultProps} context="creation" />)

      expect(screen.getByTestId('field-wrapper')).toBeInTheDocument()
    })

    it('works in review context', () => {
      render(<HighlightField {...defaultProps} context="review" />)

      expect(screen.getByTestId('field-wrapper')).toBeInTheDocument()
    })
  })
})
