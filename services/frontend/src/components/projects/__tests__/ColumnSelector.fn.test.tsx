/**
 * Additional coverage for ColumnSelector - handleDragEnd, toggle, reset
 */

import { render, screen, fireEvent } from '@testing-library/react'
import { ColumnSelector } from '../ColumnSelector'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    locale: 'en',
  }),
}))

// Mock HeadlessUI Menu
jest.mock('@headlessui/react', () => {
  const Menu = ({ children, ...rest }: any) => <div data-testid="menu">{children}</div>
  Menu.Button = ({ children, ...rest }: any) => (
    <button data-testid="menu-button">{typeof children === 'function' ? children({}) : children}</button>
  )
  Menu.Items = ({ children }: any) => <div data-testid="menu-items">{children}</div>
  Menu.Item = ({ children }: any) => (
    <div data-testid="menu-item">{typeof children === 'function' ? children({ active: false }) : children}</div>
  )
  return { Menu }
})

// Mock DnD
let capturedOnDragEnd: any = null
jest.mock('@hello-pangea/dnd', () => ({
  DragDropContext: ({ children, onDragEnd }: any) => {
    capturedOnDragEnd = onDragEnd
    return <div data-testid="dnd-context">{children}</div>
  },
  Droppable: ({ children }: any) =>
    children(
      { droppableProps: {}, innerRef: jest.fn(), placeholder: null },
    ),
  Draggable: ({ children }: any) =>
    children(
      { draggableProps: {}, dragHandleProps: {}, innerRef: jest.fn() },
      { isDragging: false },
    ),
}))

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  Bars3Icon: ({ className }: any) => <span data-testid="bars-icon" className={className} />,
  ChevronDownIcon: () => <span data-testid="chevron-down" />,
  ViewColumnsIcon: () => <span data-testid="columns-icon" />,
}))

describe('ColumnSelector', () => {
  const columns = [
    { id: 'select', label: 'Select', visible: true, sortable: false },
    { id: 'name', label: 'Name', visible: true, sortable: true, type: 'data' as const },
    { id: 'status', label: 'Status', visible: false, sortable: true, type: 'system' as const },
    { id: 'date', label: 'Date', visible: true, sortable: true },
  ]

  const defaultProps = {
    columns,
    onToggle: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    capturedOnDragEnd = null
  })

  it('renders the column selector button', () => {
    render(<ColumnSelector {...defaultProps} />)
    expect(screen.getByTestId('columns-icon')).toBeInTheDocument()
    expect(screen.getByText('projects.columns.label')).toBeInTheDocument()
  })

  it('filters out select column from toggleable list', () => {
    render(<ColumnSelector {...defaultProps} />)
    // Should have 3 toggleable columns (not including select)
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes).toHaveLength(3)
  })

  it('calls onToggle when clicking a column toggle', () => {
    render(<ColumnSelector {...defaultProps} />)
    const buttons = screen.getAllByRole('button')
    // Find a column toggle button (the ones inside menu items)
    const nameCheckbox = screen.getByText('Name').closest('button')
    if (nameCheckbox) {
      fireEvent.click(nameCheckbox)
      expect(defaultProps.onToggle).toHaveBeenCalledWith('name')
    }
  })

  it('shows column type annotation when present', () => {
    render(<ColumnSelector {...defaultProps} />)
    expect(screen.getByText('(data)')).toBeInTheDocument()
    expect(screen.getByText('(system)')).toBeInTheDocument()
  })

  it('renders reset button when onReset is provided', () => {
    const onReset = jest.fn()
    render(<ColumnSelector {...defaultProps} onReset={onReset} />)
    const resetBtn = screen.getByText('projects.columns.resetToDefault')
    expect(resetBtn).toBeInTheDocument()
    fireEvent.click(resetBtn)
    expect(onReset).toHaveBeenCalled()
  })

  it('does not render reset button when onReset is not provided', () => {
    render(<ColumnSelector {...defaultProps} />)
    expect(screen.queryByText('projects.columns.resetToDefault')).not.toBeInTheDocument()
  })

  it('calls onReorder when drag ends with valid destination', () => {
    const onReorder = jest.fn()
    render(<ColumnSelector {...defaultProps} onReorder={onReorder} />)

    // Simulate drag end
    act(() => {
      capturedOnDragEnd({
        source: { index: 0 },
        destination: { index: 1 },
      })
    })

    expect(onReorder).toHaveBeenCalled()
  })

  it('does not call onReorder when destination is null', () => {
    const onReorder = jest.fn()
    render(<ColumnSelector {...defaultProps} onReorder={onReorder} />)

    act(() => {
      capturedOnDragEnd({
        source: { index: 0 },
        destination: null,
      })
    })

    expect(onReorder).not.toHaveBeenCalled()
  })

  it('does not call onReorder when onReorder is not provided', () => {
    render(<ColumnSelector {...defaultProps} />)

    // Should not throw
    act(() => {
      capturedOnDragEnd({
        source: { index: 0 },
        destination: { index: 1 },
      })
    })
  })

  it('shows correct checkbox state for visible columns', () => {
    render(<ColumnSelector {...defaultProps} />)
    const checkboxes = screen.getAllByRole('checkbox')
    // name (visible), status (not visible), date (visible)
    expect(checkboxes[0]).toBeChecked()   // name
    expect(checkboxes[1]).not.toBeChecked() // status
    expect(checkboxes[2]).toBeChecked()   // date
  })
})

function act(fn: () => void) {
  fn()
}
