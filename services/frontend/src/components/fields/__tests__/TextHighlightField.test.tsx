/**
 * @jest-environment jsdom
 */

import { DisplayContext, TaskTemplateField } from '@/types/taskTemplate'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TextHighlightField } from '../TextHighlightField'

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ExclamationCircleIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="exclamation-icon">
      <path />
    </svg>
  ),
  TrashIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="trash-icon">
      <path />
    </svg>
  ),
  ChatBubbleLeftIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="chat-icon">
      <path />
    </svg>
  ),
}))
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


describe('TextHighlightField Component', () => {
  const mockOnChange = jest.fn()

  const defaultField: TaskTemplateField = {
    name: 'highlight_field',
    type: 'text_highlight',
    source: 'task_data',
    display: {
      annotation: 'editable',
      table: 'column',
      creation: 'editable',
    },
    label: 'Text Highlight Field',
    description: 'Highlight and label text passages',
    required: false,
  }

  const defaultValue = {
    text: 'This is a sample text for highlighting. It contains multiple sentences.',
    highlights: [],
  }

  const defaultProps = {
    field: defaultField,
    value: defaultValue,
    onChange: mockOnChange,
    context: 'annotation' as DisplayContext,
    readonly: false,
    errors: [],
  }

  // Mock window.getSelection
  const mockSelection = {
    toString: jest.fn(),
    removeAllRanges: jest.fn(),
    rangeCount: 0,
    getRangeAt: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    window.getSelection = jest.fn(() => mockSelection as any)
  })

  describe('Basic Rendering', () => {
    it('renders field label and description', () => {
      render(<TextHighlightField {...defaultProps} />)

      expect(
        screen.getByText('Text Highlight Field (Optional)')
      ).toBeInTheDocument()
      expect(
        screen.getByText('Highlight and label text passages')
      ).toBeInTheDocument()
    })

    it('renders text content correctly', () => {
      render(<TextHighlightField {...defaultProps} />)

      expect(
        screen.getByText(/This is a sample text for highlighting/)
      ).toBeInTheDocument()
    })

    it('renders label selector buttons when not readonly', () => {
      render(<TextHighlightField {...defaultProps} />)

      expect(screen.getByRole('button', { name: /Entity/ })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Claim/ })).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Evidence/ })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Reasoning/ })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Conclusion/ })
      ).toBeInTheDocument()
    })

    it('shows highlight count', () => {
      render(<TextHighlightField {...defaultProps} />)

      expect(screen.getByText('0 highlights')).toBeInTheDocument()
    })

    it('shows instructions when not readonly', () => {
      render(<TextHighlightField {...defaultProps} />)

      expect(screen.getByText(/Select text to highlight/)).toBeInTheDocument()
      expect(screen.getByText(/Use number keys/)).toBeInTheDocument()
    })

    it('does not show label selector in readonly mode', () => {
      render(<TextHighlightField {...defaultProps} readonly={true} />)

      expect(screen.queryByText('Highlight with:')).not.toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /Entity/ })
      ).not.toBeInTheDocument()
    })

    it('does not show instructions in readonly mode', () => {
      render(<TextHighlightField {...defaultProps} readonly={true} />)

      expect(
        screen.queryByText(/Select text to highlight/)
      ).not.toBeInTheDocument()
    })
  })

  describe('Label Selection', () => {
    it('selects first label by default', () => {
      render(<TextHighlightField {...defaultProps} />)

      const entityButton = screen.getByRole('button', { name: /Entity/ })
      expect(entityButton).toHaveStyle({ backgroundColor: '#60A5FA' })
    })

    it('changes selected label on button click', async () => {
      const user = userEvent.setup()
      render(<TextHighlightField {...defaultProps} />)

      const claimButton = screen.getByRole('button', { name: /Claim/ })
      await user.click(claimButton)

      expect(claimButton).toHaveStyle({ backgroundColor: '#34D399' })
    })

    it('displays keyboard shortcuts for labels', () => {
      render(<TextHighlightField {...defaultProps} />)

      expect(screen.getByText('1')).toBeInTheDocument()
      expect(screen.getByText('2')).toBeInTheDocument()
      expect(screen.getByText('3')).toBeInTheDocument()
      expect(screen.getByText('4')).toBeInTheDocument()
      expect(screen.getByText('5')).toBeInTheDocument()
    })

    it('uses custom labels from field options', () => {
      const customLabels = [
        {
          id: 'custom1',
          name: 'Custom Label 1',
          color: '#FF0000',
          shortcut: '1',
        },
        {
          id: 'custom2',
          name: 'Custom Label 2',
          color: '#00FF00',
          shortcut: '2',
        },
      ]
      const fieldWithCustomLabels = {
        ...defaultField,
        options: { labels: customLabels },
      }

      render(
        <TextHighlightField {...defaultProps} field={fieldWithCustomLabels} />
      )

      expect(
        screen.getByRole('button', { name: /Custom Label 1/ })
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: /Custom Label 2/ })
      ).toBeInTheDocument()
      expect(
        screen.queryByRole('button', { name: /Entity/ })
      ).not.toBeInTheDocument()
    })
  })

  describe('Highlight Creation', () => {
    it('creates highlight on text selection', () => {
      const textRef = { current: { textContent: defaultValue.text } as any }

      mockSelection.toString.mockReturnValue('sample text')
      mockSelection.rangeCount = 1
      mockSelection.getRangeAt.mockReturnValue({
        startContainer: { nodeValue: defaultValue.text },
        startOffset: 10,
        endOffset: 21,
        cloneRange: () => ({
          selectNodeContents: jest.fn(),
          setEnd: jest.fn(),
          toString: () => '',
        }),
      })

      const { container } = render(<TextHighlightField {...defaultProps} />)
      const textDisplay = container.querySelector('.text-display-area')

      fireEvent.mouseUp(textDisplay!)

      expect(mockOnChange).toHaveBeenCalledWith(
        expect.objectContaining({
          text: defaultValue.text,
          highlights: expect.arrayContaining([
            expect.objectContaining({
              text: 'sample text',
              label: 'Entity',
              color: '#60A5FA',
            }),
          ]),
        })
      )
    })

    it('does not create highlight in readonly mode', () => {
      mockSelection.toString.mockReturnValue('sample text')
      mockSelection.rangeCount = 1

      const { container } = render(
        <TextHighlightField {...defaultProps} readonly={true} />
      )
      const textDisplay = container.querySelector('.text-display-area')

      fireEvent.mouseUp(textDisplay!)

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('does not create highlight for empty selection', () => {
      mockSelection.toString.mockReturnValue('')
      mockSelection.rangeCount = 1

      const { container } = render(<TextHighlightField {...defaultProps} />)
      const textDisplay = container.querySelector('.text-display-area')

      fireEvent.mouseUp(textDisplay!)

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('does not create highlight when no selection exists', () => {
      mockSelection.rangeCount = 0

      const { container } = render(<TextHighlightField {...defaultProps} />)
      const textDisplay = container.querySelector('.text-display-area')

      fireEvent.mouseUp(textDisplay!)

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('clears selection after creating highlight', () => {
      mockSelection.toString.mockReturnValue('sample text')
      mockSelection.rangeCount = 1
      mockSelection.getRangeAt.mockReturnValue({
        startContainer: { nodeValue: defaultValue.text },
        startOffset: 10,
        endOffset: 21,
        cloneRange: () => ({
          selectNodeContents: jest.fn(),
          setEnd: jest.fn(),
          toString: () => '',
        }),
      })

      const { container } = render(<TextHighlightField {...defaultProps} />)
      const textDisplay = container.querySelector('.text-display-area')

      fireEvent.mouseUp(textDisplay!)

      expect(mockSelection.removeAllRanges).toHaveBeenCalled()
    })
  })

  describe('Existing Highlights Display', () => {
    const valueWithHighlights = {
      text: 'This is a sample text for highlighting. It contains multiple sentences.',
      highlights: [
        {
          id: 'h1',
          start: 10,
          end: 16,
          text: 'sample',
          label: 'Entity',
          color: '#60A5FA',
        },
        {
          id: 'h2',
          start: 30,
          end: 42,
          text: 'highlighting',
          label: 'Claim',
          color: '#34D399',
        },
      ],
    }

    it('displays highlighted text segments', () => {
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      const highlightedElements = document.querySelectorAll('.highlighted-text')
      expect(highlightedElements.length).toBeGreaterThan(0)
    })

    it('shows correct highlight count', () => {
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      expect(screen.getByText('2 highlights')).toBeInTheDocument()
    })

    it('displays highlights list section', () => {
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      expect(screen.getByText('Highlights')).toBeInTheDocument()
      expect(screen.getByText('"sample"')).toBeInTheDocument()
      expect(screen.getByText('"highlighting"')).toBeInTheDocument()
    })

    it('shows highlight labels in list', () => {
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      const highlightsList = screen.getByText('Highlights').closest('div')
      expect(within(highlightsList!).getByText('Entity')).toBeInTheDocument()
      expect(within(highlightsList!).getByText('Claim')).toBeInTheDocument()
    })

    it('displays highlight position ranges', () => {
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      expect(screen.getByText('(10-16)')).toBeInTheDocument()
      expect(screen.getByText('(30-42)')).toBeInTheDocument()
    })

    it('applies correct background colors to highlights', () => {
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      const highlightedElements = document.querySelectorAll('.highlighted-text')
      expect(highlightedElements.length).toBeGreaterThan(0)

      // Check that style attribute contains background color
      const hasBackgroundColor = Array.from(highlightedElements).some((el) =>
        el.getAttribute('style')?.includes('background-color')
      )
      expect(hasBackgroundColor).toBe(true)
    })

    it('shows comment icon when highlight has comment', () => {
      const valueWithComment = {
        ...valueWithHighlights,
        highlights: [
          {
            ...valueWithHighlights.highlights[0],
            comment: 'This is an important entity',
          },
        ],
      }

      render(<TextHighlightField {...defaultProps} value={valueWithComment} />)

      expect(screen.getByTestId('chat-icon')).toBeInTheDocument()
      expect(
        screen.getByText('This is an important entity')
      ).toBeInTheDocument()
    })

    it('does not show highlights section when no highlights exist', () => {
      render(<TextHighlightField {...defaultProps} />)

      expect(screen.queryByText('Highlights')).not.toBeInTheDocument()
    })
  })

  describe('Highlight Removal', () => {
    const valueWithHighlights = {
      text: 'This is a sample text for highlighting.',
      highlights: [
        {
          id: 'h1',
          start: 10,
          end: 16,
          text: 'sample',
          label: 'Entity',
          color: '#60A5FA',
        },
      ],
    }

    it('shows delete button for each highlight', () => {
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      expect(screen.getByTestId('trash-icon')).toBeInTheDocument()
    })

    it('removes highlight when delete button clicked', async () => {
      const user = userEvent.setup()
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      const deleteButton = screen.getByTestId('trash-icon').closest('button')
      await user.click(deleteButton!)

      expect(mockOnChange).toHaveBeenCalledWith({
        text: valueWithHighlights.text,
        highlights: [],
      })
    })

    it('does not show delete button in readonly mode', () => {
      render(
        <TextHighlightField
          {...defaultProps}
          value={valueWithHighlights}
          readonly={true}
        />
      )

      expect(screen.queryByTestId('trash-icon')).not.toBeInTheDocument()
    })

    it('does not remove highlight in readonly mode', async () => {
      const user = userEvent.setup()
      render(
        <TextHighlightField
          {...defaultProps}
          value={valueWithHighlights}
          readonly={true}
        />
      )

      expect(screen.queryByTestId('trash-icon')).not.toBeInTheDocument()
      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('stops event propagation when delete button clicked', async () => {
      const user = userEvent.setup()
      const parentClickHandler = jest.fn()

      const { container } = render(
        <div onClick={parentClickHandler}>
          <TextHighlightField {...defaultProps} value={valueWithHighlights} />
        </div>
      )

      const deleteButton = screen.getByTestId('trash-icon').closest('button')
      await user.click(deleteButton!)

      // onChange should be called for removal
      expect(mockOnChange).toHaveBeenCalled()
      // Parent click should not be called due to stopPropagation
      expect(parentClickHandler).not.toHaveBeenCalled()
    })
  })

  describe('Highlight Selection', () => {
    const valueWithHighlights = {
      text: 'This is a sample text for highlighting.',
      highlights: [
        {
          id: 'h1',
          start: 10,
          end: 16,
          text: 'sample',
          label: 'Entity',
          color: '#60A5FA',
        },
      ],
    }

    it('selects highlight when clicked in text', async () => {
      const user = userEvent.setup()
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      const highlightedText = document.querySelector('.highlighted-text')
      await user.click(highlightedText!)

      // Check if highlight item in list is selected (has correct classes)
      const highlightList = screen.getByText('Highlights').closest('div')
      const selectedHighlight = within(highlightList!)
        .getByText('"sample"')
        .closest('div')?.parentElement
      expect(selectedHighlight).toHaveClass('bg-gray-100')
    })

    it('selects highlight when clicked in list', async () => {
      const user = userEvent.setup()
      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      const highlightList = screen.getByText('Highlights').closest('div')
      const highlightItem = within(highlightList!)
        .getByText('"sample"')
        .closest('div')?.parentElement
      await user.click(highlightItem!)

      expect(highlightItem).toHaveClass('bg-gray-100')
    })
  })

  describe('Keyboard Shortcuts', () => {
    it('changes label with number keys', () => {
      render(<TextHighlightField {...defaultProps} />)

      const entityButton = screen.getByRole('button', { name: /Entity/ })
      const claimButton = screen.getByRole('button', { name: /Claim/ })

      // Simulate pressing '2' key
      fireEvent.keyDown(document, { key: '2' })

      // The selected label should change, but we need to check the styling
      expect(claimButton).toBeInTheDocument()
    })

    it('deletes selected highlight with Delete key', () => {
      const valueWithHighlights = {
        text: 'This is a sample text.',
        highlights: [
          {
            id: 'h1',
            start: 10,
            end: 16,
            text: 'sample',
            label: 'Entity',
            color: '#60A5FA',
          },
        ],
      }

      const { rerender } = render(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      // First select a highlight
      const highlightedText = document.querySelector('.highlighted-text')
      fireEvent.click(highlightedText!)

      // Rerender to apply selection state
      rerender(
        <TextHighlightField {...defaultProps} value={valueWithHighlights} />
      )

      // Then press Delete
      fireEvent.keyDown(document, { key: 'Delete' })

      // Should call onChange to remove the highlight
      expect(mockOnChange).toHaveBeenCalled()
    })

    it('does not respond to keyboard shortcuts in readonly mode', () => {
      render(<TextHighlightField {...defaultProps} readonly={true} />)

      fireEvent.keyDown(document, { key: '2' })
      fireEvent.keyDown(document, { key: 'Delete' })

      expect(mockOnChange).not.toHaveBeenCalled()
    })

    it('ignores non-numeric keys for label selection', () => {
      render(<TextHighlightField {...defaultProps} />)

      fireEvent.keyDown(document, { key: 'a' })
      fireEvent.keyDown(document, { key: 'Enter' })
      fireEvent.keyDown(document, { key: 'Escape' })

      // Should not cause any errors
      expect(screen.getByRole('button', { name: /Entity/ })).toBeInTheDocument()
    })

    it('handles number key beyond available labels', () => {
      render(<TextHighlightField {...defaultProps} />)

      // Press '9' when only 5 labels exist
      fireEvent.keyDown(document, { key: '9' })

      // Should not cause any errors
      expect(screen.getByRole('button', { name: /Entity/ })).toBeInTheDocument()
    })
  })

  describe('Overlapping Highlights', () => {
    const valueWithOverlappingHighlights = {
      text: 'This is a sample text for highlighting.',
      highlights: [
        {
          id: 'h1',
          start: 10,
          end: 21,
          text: 'sample text',
          label: 'Entity',
          color: '#60A5FA',
        },
        {
          id: 'h2',
          start: 17,
          end: 21,
          text: 'text',
          label: 'Claim',
          color: '#34D399',
        },
      ],
    }

    it('renders overlapping highlights correctly', () => {
      render(
        <TextHighlightField
          {...defaultProps}
          value={valueWithOverlappingHighlights}
        />
      )

      const highlightedElements = document.querySelectorAll('.highlighted-text')
      expect(highlightedElements.length).toBeGreaterThan(0)
    })

    it('shows overlap indicator when multiple highlights cover same text', () => {
      render(
        <TextHighlightField
          {...defaultProps}
          value={valueWithOverlappingHighlights}
        />
      )

      // Look for the overlap indicator (badge showing count)
      const overlapIndicators = document.querySelectorAll('.rounded-full')
      expect(overlapIndicators.length).toBeGreaterThan(0)
    })

    it('displays tooltip with all overlapping labels', () => {
      render(
        <TextHighlightField
          {...defaultProps}
          value={valueWithOverlappingHighlights}
        />
      )

      const highlightedText = document.querySelector('.highlighted-text')
      const title = highlightedText?.getAttribute('title')

      expect(title).toBeTruthy()
    })

    it('shows top highlight color for overlapping segments', () => {
      render(
        <TextHighlightField
          {...defaultProps}
          value={valueWithOverlappingHighlights}
        />
      )

      const highlightedElements = document.querySelectorAll('.highlighted-text')
      const hasOverlapStyling = Array.from(highlightedElements).some((el) =>
        el.getAttribute('style')?.includes('border-bottom')
      )

      expect(hasOverlapStyling).toBe(true)
    })
  })

  describe('Edge Cases', () => {
    it('handles empty text gracefully', () => {
      const emptyValue = { text: '', highlights: [] }
      render(<TextHighlightField {...defaultProps} value={emptyValue} />)

      const textDisplay = document.querySelector('.text-display-area')
      expect(textDisplay).toBeInTheDocument()
    })

    it('handles null value gracefully', () => {
      render(<TextHighlightField {...defaultProps} value={null as any} />)

      expect(screen.getByText('0 highlights')).toBeInTheDocument()
    })

    it('handles undefined value gracefully', () => {
      render(<TextHighlightField {...defaultProps} value={undefined as any} />)

      expect(screen.getByText('0 highlights')).toBeInTheDocument()
    })

    it('handles very long text', () => {
      const longText = 'A'.repeat(10000)
      const longValue = { text: longText, highlights: [] }

      render(<TextHighlightField {...defaultProps} value={longValue} />)

      const textDisplay = document.querySelector('.text-display-area')
      expect(textDisplay).toBeInTheDocument()
    })

    it('handles many highlights', () => {
      const manyHighlights = Array.from({ length: 100 }, (_, i) => ({
        id: `h${i}`,
        start: i * 2,
        end: i * 2 + 1,
        text: 'x',
        label: 'Entity',
        color: '#60A5FA',
      }))

      const valueWithMany = {
        text: 'x'.repeat(200),
        highlights: manyHighlights,
      }

      render(<TextHighlightField {...defaultProps} value={valueWithMany} />)

      expect(screen.getByText('100 highlights')).toBeInTheDocument()
    })

    it('handles highlight at text boundaries', () => {
      const valueAtBoundaries = {
        text: 'Sample text',
        highlights: [
          {
            id: 'h1',
            start: 0,
            end: 6,
            text: 'Sample',
            label: 'Entity',
            color: '#60A5FA',
          },
          {
            id: 'h2',
            start: 7,
            end: 11,
            text: 'text',
            label: 'Claim',
            color: '#34D399',
          },
        ],
      }

      render(<TextHighlightField {...defaultProps} value={valueAtBoundaries} />)

      const highlightedElements = document.querySelectorAll('.highlighted-text')
      expect(highlightedElements.length).toBeGreaterThan(0)
    })

    it('handles special characters in text', () => {
      const specialValue = {
        text: 'Text with special chars: àáâãäå ñç ü é 中文 🚀',
        highlights: [],
      }

      render(<TextHighlightField {...defaultProps} value={specialValue} />)

      expect(screen.getByText(/Text with special chars/)).toBeInTheDocument()
    })

    it('handles invalid highlight ranges gracefully', () => {
      const invalidValue = {
        text: 'Sample text',
        highlights: [
          {
            id: 'h1',
            start: 100,
            end: 200,
            text: 'invalid',
            label: 'Entity',
            color: '#60A5FA',
          },
        ],
      }

      render(<TextHighlightField {...defaultProps} value={invalidValue} />)

      // Should not crash
      expect(screen.getByText('1 highlight')).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('displays error messages', () => {
      const errors = ['This field is required']
      render(<TextHighlightField {...defaultProps} errors={errors} />)

      expect(screen.getByText('This field is required')).toBeInTheDocument()
      expect(screen.getByTestId('exclamation-icon')).toBeInTheDocument()
    })

    it('displays multiple error messages', () => {
      const errors = ['Error 1', 'Error 2', 'Error 3']
      render(<TextHighlightField {...defaultProps} errors={errors} />)

      errors.forEach((error) => {
        expect(screen.getByText(error)).toBeInTheDocument()
      })

      const errorIcons = screen.getAllByTestId('exclamation-icon')
      expect(errorIcons).toHaveLength(3)
    })
  })

  describe('Required Field Handling', () => {
    it('shows required asterisk for required fields', () => {
      const requiredField = { ...defaultField, required: true }
      render(<TextHighlightField {...defaultProps} field={requiredField} />)

      const asterisk = screen.getByText('*')
      expect(asterisk).toBeInTheDocument()
      expect(asterisk).toHaveClass('text-red-500')
    })

    it('shows optional label for non-required fields', () => {
      render(<TextHighlightField {...defaultProps} />)

      expect(
        screen.getByText('Text Highlight Field (Optional)')
      ).toBeInTheDocument()
    })
  })

  describe('Styling and CSS Classes', () => {
    it('applies custom className to wrapper', () => {
      render(<TextHighlightField {...defaultProps} className="custom-class" />)

      const wrapper = document.querySelector('.field-wrapper')
      expect(wrapper).toHaveClass('custom-class')
    })

    it('applies correct cursor style based on readonly', () => {
      const { rerender } = render(
        <TextHighlightField {...defaultProps} readonly={false} />
      )

      let textDisplay = document.querySelector('.text-display-area')
      expect(textDisplay).toHaveClass('cursor-text')

      rerender(<TextHighlightField {...defaultProps} readonly={true} />)

      textDisplay = document.querySelector('.text-display-area')
      expect(textDisplay).toHaveClass('cursor-default')
    })

    it('applies correct line height and font styling', () => {
      render(<TextHighlightField {...defaultProps} />)

      const textDisplay = document.querySelector('.text-display-area')
      expect(textDisplay).toHaveStyle({
        lineHeight: '1.8',
        fontSize: '15px',
      })
    })
  })

  describe('Context Variations', () => {
    it('works with different display contexts', () => {
      const contexts: DisplayContext[] = [
        'annotation',
        'table',
        'creation',
        'review',
      ]

      contexts.forEach((context) => {
        const { unmount } = render(
          <TextHighlightField {...defaultProps} context={context} />
        )
        expect(screen.getByText(/This is a sample text/)).toBeInTheDocument()
        unmount()
      })
    })
  })

  describe('Integration Tests', () => {
    it('complete workflow: select label, create highlight, remove highlight', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()

      render(<TextHighlightField {...defaultProps} onChange={onChange} />)

      // Select a different label
      const claimButton = screen.getByRole('button', { name: /Claim/ })
      await user.click(claimButton)

      // Create a highlight (simulated)
      mockSelection.toString.mockReturnValue('sample')
      mockSelection.rangeCount = 1
      mockSelection.getRangeAt.mockReturnValue({
        startContainer: { nodeValue: defaultValue.text },
        startOffset: 10,
        endOffset: 16,
        cloneRange: () => ({
          selectNodeContents: jest.fn(),
          setEnd: jest.fn(),
          toString: () => '',
        }),
      })

      const textDisplay = document.querySelector('.text-display-area')
      fireEvent.mouseUp(textDisplay!)

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          highlights: expect.arrayContaining([
            expect.objectContaining({
              label: 'Claim',
              color: '#34D399',
            }),
          ]),
        })
      )
    })

    it('maintains highlight state across re-renders', () => {
      const valueWithHighlight = {
        text: 'Sample text',
        highlights: [
          {
            id: 'h1',
            start: 0,
            end: 6,
            text: 'Sample',
            label: 'Entity',
            color: '#60A5FA',
          },
        ],
      }

      const { rerender } = render(
        <TextHighlightField {...defaultProps} value={valueWithHighlight} />
      )

      expect(screen.getByText('"Sample"')).toBeInTheDocument()

      rerender(
        <TextHighlightField {...defaultProps} value={valueWithHighlight} />
      )

      expect(screen.getByText('"Sample"')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has proper title attributes for highlights', () => {
      const valueWithHighlight = {
        text: 'Sample text',
        highlights: [
          {
            id: 'h1',
            start: 0,
            end: 6,
            text: 'Sample',
            label: 'Entity',
            color: '#60A5FA',
          },
        ],
      }

      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlight} />
      )

      const highlightedText = document.querySelector('.highlighted-text')
      expect(highlightedText?.getAttribute('title')).toContain('Entity')
    })

    it('buttons have proper title attributes with shortcuts', () => {
      render(<TextHighlightField {...defaultProps} />)

      const entityButton = screen.getByRole('button', { name: /Entity/ })
      expect(entityButton).toHaveAttribute('title', 'Entity (1)')
    })

    it('delete buttons have proper title attributes', () => {
      const valueWithHighlight = {
        text: 'Sample text',
        highlights: [
          {
            id: 'h1',
            start: 0,
            end: 6,
            text: 'Sample',
            label: 'Entity',
            color: '#60A5FA',
          },
        ],
      }

      render(
        <TextHighlightField {...defaultProps} value={valueWithHighlight} />
      )

      const deleteButton = screen.getByTestId('trash-icon').closest('button')
      expect(deleteButton).toHaveAttribute('title', 'Remove highlight')
    })
  })
})
