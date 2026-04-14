/**
 * Tests for MilkdownEditor component
 * Tests rendering, toolbar display, wrapper structure, class propagation,
 * and minHeight prop. Milkdown library is fully mocked via manual module resolution.
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'

// Mock I18n
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))

// Mock heroicons
jest.mock('@heroicons/react/20/solid', () => ({
  ChevronDownIcon: ({ className }: any) => <svg data-testid="chevron-down" className={className} />,
  ChevronUpIcon: ({ className }: any) => <svg data-testid="chevron-up" className={className} />,
}))

// Mock legalHeadingUtils
jest.mock('@/lib/utils/legalHeadingUtils', () => ({
  LEGAL_LEVELS: [
    { level: 1, prefix: 'A.', mdLevel: 1 },
    { level: 2, prefix: 'I.', mdLevel: 2 },
    { level: 3, prefix: '1.', mdLevel: 3 },
    { level: 4, prefix: 'a)', mdLevel: 4 },
    { level: 5, prefix: 'aa)', mdLevel: 5 },
    { level: 6, prefix: '(1)', mdLevel: 6 },
  ],
  extractHeadingsFromMarkdown: jest.fn(() => []),
  getNextPrefix: jest.fn(() => 'A.'),
}))

// ESM-only Milkdown packages cannot be resolved by Jest's CJS resolver.
// Instead of mocking individual @milkdown/* packages, we mock the entire
// MilkdownEditor module so the test can exercise the public API surface.
// The internal EditorComponent+EditorToolbar are rendered via a lightweight
// substitute that mimics the real component's DOM structure.

const mockOnChange = jest.fn()

// Mutable mock editor instance that tests can configure
const mockEditorState = {
  editor: null as any,
  loading: false,
}

const mockAction = jest.fn((fn: any) => fn)
const mockEditorViewState = {
  doc: {
    content: { size: 10 },
    textBetween: jest.fn(() => ''),
    descendants: jest.fn(() => true),
  },
  selection: { from: 0, to: 0 },
  tr: { setSelection: jest.fn().mockReturnThis() },
}
const mockView = {
  state: mockEditorViewState,
  dispatch: jest.fn(),
  focus: jest.fn(),
}

const createMockEditor = () => ({
  ctx: {
    get: jest.fn((ctx: string) => {
      if (ctx === 'editorViewCtx') return mockView
      if (ctx === 'serializerCtx') return jest.fn(() => '# A. Test\n\nSome content')
      return {}
    }),
  },
  action: mockAction,
})

jest.mock('@milkdown/react', () => ({
  Milkdown: () => <div data-testid="milkdown-editor">Editor</div>,
  MilkdownProvider: ({ children }: any) => <div data-testid="milkdown-provider">{children}</div>,
  useEditor: () => ({ get: jest.fn() }),
  useInstance: () => [mockEditorState.loading, jest.fn(() => mockEditorState.editor)],
}), { virtual: true })

jest.mock('@milkdown/core', () => ({
  defaultValueCtx: 'defaultValueCtx',
  editorViewCtx: 'editorViewCtx',
  rootCtx: 'rootCtx',
  serializerCtx: 'serializerCtx',
  Editor: { make: jest.fn(() => ({ config: jest.fn().mockReturnThis(), use: jest.fn().mockReturnThis() })) },
}), { virtual: true })

jest.mock('@milkdown/preset-commonmark', () => ({
  commonmark: jest.fn(),
  toggleStrongCommand: { key: 'toggleStrong' },
  toggleEmphasisCommand: { key: 'toggleEmphasis' },
  wrapInBulletListCommand: { key: 'wrapInBulletList' },
  wrapInOrderedListCommand: { key: 'wrapInOrderedList' },
}), { virtual: true })

jest.mock('@milkdown/plugin-listener', () => ({
  listener: jest.fn(),
  listenerCtx: 'listenerCtx',
}), { virtual: true })

jest.mock('@milkdown/plugin-history', () => ({
  history: jest.fn(),
}), { virtual: true })

jest.mock('@milkdown/utils', () => ({
  callCommand: jest.fn((key: string) => key),
  replaceAll: jest.fn((value: string) => value),
}), { virtual: true })

jest.mock('prosemirror-state', () => ({
  TextSelection: { create: jest.fn() },
}), { virtual: true })

import { MilkdownEditor } from '../MilkdownEditor'

describe('MilkdownEditor', () => {
  const defaultProps = {
    value: '# Test Heading\n\nSome content',
    onChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  // --- Basic Rendering ---

  it('renders without crashing', () => {
    const { container } = render(<MilkdownEditor {...defaultProps} />)
    expect(container).toBeTruthy()
  })

  it('renders the milkdown-wrapper div', () => {
    const { container } = render(<MilkdownEditor {...defaultProps} />)
    const wrapper = container.querySelector('.milkdown-wrapper')
    expect(wrapper).toBeInTheDocument()
  })

  it('renders the MilkdownProvider', () => {
    render(<MilkdownEditor {...defaultProps} />)
    expect(screen.getByTestId('milkdown-provider')).toBeInTheDocument()
  })

  it('renders the Milkdown editor component', () => {
    render(<MilkdownEditor {...defaultProps} />)
    expect(screen.getByTestId('milkdown-editor')).toBeInTheDocument()
  })

  it('injects editor CSS styles', () => {
    const { container } = render(<MilkdownEditor {...defaultProps} />)
    const styleTag = container.querySelector('style')
    expect(styleTag).toBeInTheDocument()
    expect(styleTag?.textContent).toContain('.milkdown-wrapper')
  })

  // --- CSS Custom Property for minHeight ---

  it('sets --editor-min-height CSS variable from minHeight prop', () => {
    const { container } = render(
      <MilkdownEditor {...defaultProps} minHeight={400} />
    )
    const wrapper = container.querySelector('.milkdown-wrapper') as HTMLElement
    expect(wrapper.style.getPropertyValue('--editor-min-height')).toBe('400px')
  })

  it('defaults minHeight to 200px', () => {
    const { container } = render(<MilkdownEditor {...defaultProps} />)
    const wrapper = container.querySelector('.milkdown-wrapper') as HTMLElement
    expect(wrapper.style.getPropertyValue('--editor-min-height')).toBe('200px')
  })

  // --- className Prop ---

  it('applies custom className to the wrapper', () => {
    const { container } = render(
      <MilkdownEditor {...defaultProps} className="custom-editor-class" />
    )
    const wrapper = container.querySelector('.milkdown-wrapper')
    expect(wrapper?.className).toContain('custom-editor-class')
  })

  it('applies default classes when no className is provided', () => {
    const { container } = render(<MilkdownEditor {...defaultProps} />)
    const wrapper = container.querySelector('.milkdown-wrapper')
    expect(wrapper?.className).toContain('rounded-lg')
    expect(wrapper?.className).toContain('border')
  })

  // --- Toolbar ---

  it('does not show toolbar by default (showToolbar=false)', () => {
    render(<MilkdownEditor {...defaultProps} />)
    // Toolbar legal level buttons should not be rendered
    expect(screen.queryByTitle(/labeling.milkdown.level/)).not.toBeInTheDocument()
  })

  it('shows toolbar when showToolbar is true', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    // Should render legal level buttons
    expect(screen.getByText('A.')).toBeInTheDocument()
    expect(screen.getByText('I.')).toBeInTheDocument()
    expect(screen.getByText('1.')).toBeInTheDocument()
    expect(screen.getByText('a)')).toBeInTheDocument()
  })

  it('shows bold and italic buttons in toolbar', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(screen.getByTitle('labeling.milkdown.bold')).toBeInTheDocument()
    expect(screen.getByTitle('labeling.milkdown.italic')).toBeInTheDocument()
  })

  it('shows promote/demote buttons in toolbar', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(screen.getByTitle('labeling.milkdown.promoteLevel')).toBeInTheDocument()
    expect(screen.getByTitle('labeling.milkdown.demoteLevel')).toBeInTheDocument()
  })

  it('shows bullet and ordered list buttons in toolbar', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(screen.getByTitle('labeling.milkdown.bulletList')).toBeInTheDocument()
    expect(screen.getByTitle('labeling.milkdown.orderedList')).toBeInTheDocument()
  })

  it('renders all 6 legal heading level buttons', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(screen.getByText('A.')).toBeInTheDocument()
    expect(screen.getByText('I.')).toBeInTheDocument()
    expect(screen.getByText('1.')).toBeInTheDocument()
    expect(screen.getByText('a)')).toBeInTheDocument()
    expect(screen.getByText('aa)')).toBeInTheDocument()
    expect(screen.getByText('(1)')).toBeInTheDocument()
  })

  // --- Toolbar Button Interactions ---

  it('does not throw when bold button is clicked', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(() => {
      fireEvent.click(screen.getByTitle('labeling.milkdown.bold'))
    }).not.toThrow()
  })

  it('does not throw when italic button is clicked', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(() => {
      fireEvent.click(screen.getByTitle('labeling.milkdown.italic'))
    }).not.toThrow()
  })

  it('does not throw when promote button is clicked', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(() => {
      fireEvent.click(screen.getByTitle('labeling.milkdown.promoteLevel'))
    }).not.toThrow()
  })

  it('does not throw when demote button is clicked', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(() => {
      fireEvent.click(screen.getByTitle('labeling.milkdown.demoteLevel'))
    }).not.toThrow()
  })

  it('does not throw when bullet list button is clicked', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(() => {
      fireEvent.click(screen.getByTitle('labeling.milkdown.bulletList'))
    }).not.toThrow()
  })

  it('does not throw when ordered list button is clicked', () => {
    render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
    expect(() => {
      fireEvent.click(screen.getByTitle('labeling.milkdown.orderedList'))
    }).not.toThrow()
  })

  // --- Editor Styles ---

  it('includes dark mode styles', () => {
    const { container } = render(<MilkdownEditor {...defaultProps} />)
    const styleTag = container.querySelector('style')
    expect(styleTag?.textContent).toContain('.dark .milkdown-wrapper')
  })

  it('includes heading styles (h1-h6)', () => {
    const { container } = render(<MilkdownEditor {...defaultProps} />)
    const styleTag = container.querySelector('style')
    expect(styleTag?.textContent).toContain('.milkdown-wrapper h1')
    expect(styleTag?.textContent).toContain('.milkdown-wrapper h6')
  })

  it('includes list styles', () => {
    const { container } = render(<MilkdownEditor {...defaultProps} />)
    const styleTag = container.querySelector('style')
    expect(styleTag?.textContent).toContain('.milkdown-wrapper ul')
    expect(styleTag?.textContent).toContain('.milkdown-wrapper ol')
  })

  // --- Edge Cases ---

  it('renders with empty value', () => {
    const { container } = render(
      <MilkdownEditor value="" onChange={jest.fn()} />
    )
    expect(container).toBeTruthy()
    expect(screen.getByTestId('milkdown-editor')).toBeInTheDocument()
  })

  it('renders with very long value', () => {
    const longValue = '# Heading\n\n' + 'Paragraph text. '.repeat(1000)
    const { container } = render(
      <MilkdownEditor value={longValue} onChange={jest.fn()} />
    )
    expect(container).toBeTruthy()
  })

  it('has focus ring styling on the wrapper', () => {
    const { container } = render(<MilkdownEditor {...defaultProps} />)
    const wrapper = container.querySelector('.milkdown-wrapper')
    expect(wrapper?.className).toContain('focus-within:ring-2')
  })

  // --- Toolbar Handler Tests with Mock Editor ---

  describe('Toolbar with active editor', () => {
    beforeEach(() => {
      mockEditorState.loading = false
      mockEditorState.editor = createMockEditor()
      jest.clearAllMocks()
    })

    afterEach(() => {
      mockEditorState.editor = null
    })

    it('calls editor action when bold button is clicked with active editor', () => {
      render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
      fireEvent.click(screen.getByTitle('labeling.milkdown.bold'))
      expect(mockEditorState.editor.action).toHaveBeenCalled()
    })

    it('calls editor action when italic button is clicked with active editor', () => {
      render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
      fireEvent.click(screen.getByTitle('labeling.milkdown.italic'))
      expect(mockEditorState.editor.action).toHaveBeenCalled()
    })

    it('calls editor action for legal heading level button', () => {
      render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
      fireEvent.click(screen.getByText('A.'))
      // Should access editor context for serializer and view
      expect(mockEditorState.editor.ctx.get).toHaveBeenCalled()
    })

    it('calls editor action for bullet list button', () => {
      render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
      fireEvent.click(screen.getByTitle('labeling.milkdown.bulletList'))
      // Should call the bullet list command
      expect(mockEditorState.editor.action).toHaveBeenCalled()
    })

    it('calls editor action for ordered list button', () => {
      render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
      fireEvent.click(screen.getByTitle('labeling.milkdown.orderedList'))
      expect(mockEditorState.editor.action).toHaveBeenCalled()
    })

    it('calls promote handler with active editor', () => {
      render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
      fireEvent.click(screen.getByTitle('labeling.milkdown.promoteLevel'))
      expect(mockEditorState.editor.ctx.get).toHaveBeenCalled()
    })

    it('calls demote handler with active editor', () => {
      render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
      fireEvent.click(screen.getByTitle('labeling.milkdown.demoteLevel'))
      expect(mockEditorState.editor.ctx.get).toHaveBeenCalled()
    })

    it('does not throw when all level buttons are clicked', () => {
      render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
      expect(() => {
        fireEvent.click(screen.getByText('A.'))
        fireEvent.click(screen.getByText('I.'))
        fireEvent.click(screen.getByText('1.'))
        fireEvent.click(screen.getByText('a)'))
        fireEvent.click(screen.getByText('aa)'))
        fireEvent.click(screen.getByText('(1)'))
      }).not.toThrow()
    })
  })

  describe('Toolbar in loading state', () => {
    beforeEach(() => {
      mockEditorState.loading = true
      mockEditorState.editor = null
    })

    afterEach(() => {
      mockEditorState.loading = false
    })

    it('does not crash when buttons clicked during loading', () => {
      render(<MilkdownEditor {...defaultProps} showToolbar={true} />)
      expect(() => {
        fireEvent.click(screen.getByTitle('labeling.milkdown.bold'))
        fireEvent.click(screen.getByTitle('labeling.milkdown.italic'))
        fireEvent.click(screen.getByTitle('labeling.milkdown.promoteLevel'))
        fireEvent.click(screen.getByTitle('labeling.milkdown.demoteLevel'))
        fireEvent.click(screen.getByTitle('labeling.milkdown.bulletList'))
        fireEvent.click(screen.getByTitle('labeling.milkdown.orderedList'))
        fireEvent.click(screen.getByText('A.'))
      }).not.toThrow()
    })
  })
})
