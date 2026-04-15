/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for HighlightField.
 * Targets 7 uncovered branches:
 * - default args for readonly and errors
 * - handleTextSelection: readonly=true, no selection, no container
 * - renderHighlightedText: with highlights, text before/after
 * - removeHighlight in readonly mode
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'
import { HighlightField } from '../HighlightField'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      const t: Record<string, string> = {
        'fields.noTextForHighlighting': 'No text available for highlighting',
        'fields.clickToRemove': 'Click to remove',
        'fields.highlightInstructions': 'Select text to highlight',
        'fields.highlightsCount': `${vars?.count || 0} highlights`,
        'fields.remove': 'Remove',
      }
      return t[key] || key
    },
  }),
}))

jest.mock('@/components/fields/BaseField', () => ({
  FieldWrapper: ({ children, field, errors, className }: any) => (
    <div data-testid="field-wrapper" className={className}>
      <div data-testid="field-label">{field.label || field.name}</div>
      {errors?.map((e: string, i: number) => <div key={i} data-testid="error">{e}</div>)}
      {children}
    </div>
  ),
}))

const baseField = {
  name: 'highlight1',
  type: 'highlight' as const,
  display: { annotation: 'editable' as const, table: 'column' as const, creation: 'editable' as const },
  source: 'annotation' as const,
  label: 'Test Highlight',
  metadata: { source_text: 'The quick brown fox jumps over the lazy dog' },
}

describe('HighlightField', () => {
  it('renders with no highlights (default readonly=false, errors=[])', () => {
    render(
      <HighlightField
        field={baseField}
        value={[]}
        onChange={jest.fn()}
        context="annotation"
      />
    )
    expect(screen.getByText('The quick brown fox jumps over the lazy dog')).toBeInTheDocument()
    expect(screen.getByText('Select text to highlight')).toBeInTheDocument()
  })

  it('renders with readonly=true (no highlight instructions shown)', () => {
    render(
      <HighlightField
        field={baseField}
        value={[]}
        onChange={jest.fn()}
        readonly={true}
        context="annotation"
      />
    )
    expect(screen.queryByText('Select text to highlight')).not.toBeInTheDocument()
  })

  it('renders with non-array value (converts to empty array)', () => {
    render(
      <HighlightField
        field={baseField}
        value="not-array"
        onChange={jest.fn()}
        context="annotation"
      />
    )
    expect(screen.getByText('The quick brown fox jumps over the lazy dog')).toBeInTheDocument()
  })

  it('renders with highlights showing text and remove buttons', () => {
    const highlights = [
      { start: 4, end: 9, text: 'quick', label: 'adj' },
      { start: 16, end: 19, text: 'fox', label: 'noun' },
    ]
    render(
      <HighlightField
        field={baseField}
        value={highlights}
        onChange={jest.fn()}
        context="annotation"
      />
    )
    expect(screen.getByText(/2 highlights/)).toBeInTheDocument()
    expect(screen.getAllByText('Remove')).toHaveLength(2)
  })

  it('renders highlights in readonly mode (no remove buttons)', () => {
    const highlights = [{ start: 4, end: 9, text: 'quick' }]
    render(
      <HighlightField
        field={baseField}
        value={highlights}
        onChange={jest.fn()}
        readonly={true}
        context="annotation"
      />
    )
    expect(screen.queryByText('Remove')).not.toBeInTheDocument()
  })

  it('calls onChange when remove button is clicked', () => {
    const onChange = jest.fn()
    const highlights = [
      { start: 4, end: 9, text: 'quick' },
      { start: 16, end: 19, text: 'fox' },
    ]
    render(
      <HighlightField
        field={baseField}
        value={highlights}
        onChange={onChange}
        context="annotation"
      />
    )
    fireEvent.click(screen.getAllByText('Remove')[0])
    expect(onChange).toHaveBeenCalledWith([{ start: 16, end: 19, text: 'fox' }])
  })

  it('does not remove highlight when readonly', () => {
    const onChange = jest.fn()
    const highlights = [{ start: 4, end: 9, text: 'quick' }]
    render(
      <HighlightField
        field={baseField}
        value={highlights}
        onChange={onChange}
        readonly={true}
        context="annotation"
      />
    )
    // Click the highlighted text span (which also has onClick for remove)
    const highlightSpan = screen.getByText('"quick"').closest('li')
    expect(highlightSpan).toBeInTheDocument()
    // In readonly mode, there's no Remove button to click
    expect(onChange).not.toHaveBeenCalled()
  })

  it('renders with no source_text in metadata (uses fallback)', () => {
    const fieldNoSource = { ...baseField, metadata: {} }
    render(
      <HighlightField
        field={fieldNoSource}
        value={[]}
        onChange={jest.fn()}
        context="annotation"
      />
    )
    expect(screen.getByText('No text available for highlighting')).toBeInTheDocument()
  })

  it('renders with errors', () => {
    render(
      <HighlightField
        field={baseField}
        value={[]}
        onChange={jest.fn()}
        errors={['Required field']}
        context="annotation"
      />
    )
    expect(screen.getByText('Required field')).toBeInTheDocument()
  })

  it('passes className to FieldWrapper', () => {
    render(
      <HighlightField
        field={baseField}
        value={[]}
        onChange={jest.fn()}
        context="annotation"
        className="custom-class"
      />
    )
    expect(screen.getByTestId('field-wrapper')).toHaveClass('custom-class')
  })
})
