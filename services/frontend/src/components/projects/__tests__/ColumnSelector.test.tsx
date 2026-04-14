/**
 * Comprehensive test suite for ColumnSelector component
 * Target: 90%+ code coverage
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ColumnSelector } from '../ColumnSelector'

// Mock I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'projects.columns.label': 'Columns',
        'projects.columns.showHideReorder': 'Show/Hide & Reorder Columns',
        'projects.columns.resetToDefault': 'Reset to Default',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

const mockColumns = [
  {
    id: 'select',
    label: 'Select',
    visible: true,
    sortable: false,
    type: 'system' as const,
  },
  {
    id: 'id',
    label: 'ID',
    visible: true,
    sortable: true,
    type: 'system' as const,
  },
  {
    id: 'title',
    label: 'Title',
    visible: true,
    sortable: true,
    type: 'data' as const,
  },
  {
    id: 'description',
    label: 'Description',
    visible: false,
    sortable: false,
    type: 'data' as const,
  },
  {
    id: 'author',
    label: 'Author',
    visible: true,
    sortable: true,
    type: 'metadata' as const,
  },
  {
    id: 'created_at',
    label: 'Created At',
    visible: false,
    sortable: true,
    type: 'system' as const,
  },
]

describe('ColumnSelector', () => {
  const mockOnToggle = jest.fn()
  const mockOnReorder = jest.fn()
  const mockOnReset = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Initial Rendering', () => {
    it('should render the Columns button', () => {
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)
      expect(
        screen.getByRole('button', { name: /columns/i })
      ).toBeInTheDocument()
    })

    it('should display column icon', () => {
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )
      const icon = container.querySelector('svg')
      expect(icon).toBeInTheDocument()
    })

    it('should display chevron down icon', () => {
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )
      const icons = container.querySelectorAll('svg')
      expect(icons.length).toBeGreaterThan(1)
    })

    it('should render with outline variant button', () => {
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)
      const button = screen.getByRole('button', { name: /columns/i })
      // Button uses outline variant which includes ring-1 and ring-inset classes
      expect(button).toHaveClass('ring-1')
      expect(button).toHaveClass('ring-inset')
    })
  })

  describe('Menu Opening', () => {
    it('should open menu when button clicked', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        expect(
          screen.getByText('Show/Hide & Reorder Columns')
        ).toBeInTheDocument()
      })
    })

    it('should display header text when menu is open', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        expect(
          screen.getByText('Show/Hide & Reorder Columns')
        ).toBeInTheDocument()
      })
    })

    it('should display drag icon in header', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const dragIcons = container.querySelectorAll('svg')
        expect(dragIcons.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Column List Display', () => {
    it('should display all toggleable columns', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByText('ID')).toBeInTheDocument()
        expect(screen.getByText('Title')).toBeInTheDocument()
        expect(screen.getByText('Description')).toBeInTheDocument()
        expect(screen.getByText('Author')).toBeInTheDocument()
        expect(screen.getByText('Created At')).toBeInTheDocument()
      })
    })

    it('should not display select column in list', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        // "Select" text should not appear in column list
        const selectTexts = screen.queryAllByText('Select')
        expect(selectTexts.length).toBe(0)
      })
    })

    it('should display column types in labels', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        // Column types are shown in parentheses as spans
        const typeLabels = container.querySelectorAll('.text-xs.text-zinc-500')
        expect(typeLabels.length).toBeGreaterThan(0)
        const typesText = Array.from(typeLabels)
          .map((el) => el.textContent)
          .join(' ')
        expect(typesText).toContain('(system)')
        expect(typesText).toContain('(data)')
        expect(typesText).toContain('(metadata)')
      })
    })

    it('should show checkboxes for all columns', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const checkboxes = container.querySelectorAll('input[type="checkbox"]')
        expect(checkboxes.length).toBe(5) // All except 'select'
      })
    })

    it('should show checked state for visible columns', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const checkboxes = container.querySelectorAll('input[type="checkbox"]')
        const checkedBoxes = Array.from(checkboxes).filter(
          (cb) => (cb as HTMLInputElement).checked
        )
        expect(checkedBoxes.length).toBe(3) // id, title, author
      })
    })

    it('should show unchecked state for hidden columns', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const checkboxes = container.querySelectorAll('input[type="checkbox"]')
        const uncheckedBoxes = Array.from(checkboxes).filter(
          (cb) => !(cb as HTMLInputElement).checked
        )
        expect(uncheckedBoxes.length).toBe(2) // description, created_at
      })
    })

    it('should display drag handles for all columns', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const dragHandles = container.querySelectorAll('[class*="cursor-move"]')
        expect(dragHandles.length).toBe(5) // All toggleable columns
      })
    })
  })

  describe('Column Toggle Functionality', () => {
    it('should call onToggle when column is clicked', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(async () => {
        const titleButton = screen.getByText('Title').closest('button')
        await user.click(titleButton!)
        expect(mockOnToggle).toHaveBeenCalledWith('title')
      })
    })

    it('should call onToggle with correct column id', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(async () => {
        const descriptionButton = screen
          .getByText('Description')
          .closest('button')
        await user.click(descriptionButton!)
        expect(mockOnToggle).toHaveBeenCalledWith('description')
      })
    })

    it('should handle clicking on column rows', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(async () => {
        const titleButton = screen.getByText('Title').closest('button')
        await user.click(titleButton!)
        expect(mockOnToggle).toHaveBeenCalled()
      })
    })

    it('should allow toggling of visible columns', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(async () => {
        const titleButton = screen.getByText('Title').closest('button')
        await user.click(titleButton!)
        expect(mockOnToggle).toHaveBeenCalledWith('title')
      })
    })
  })

  describe('Drag and Drop Functionality', () => {
    it('should render drag handles when onReorder is provided', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector
          columns={mockColumns}
          onToggle={mockOnToggle}
          onReorder={mockOnReorder}
        />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const dragHandle = container.querySelector('.cursor-move')
        expect(dragHandle).toBeInTheDocument()
      })
    })

    it('should show cursor-move class on drag handles', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector
          columns={mockColumns}
          onToggle={mockOnToggle}
          onReorder={mockOnReorder}
        />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const dragHandle = container.querySelector('.cursor-move')
        expect(dragHandle).toBeInTheDocument()
      })
    })

    it('should have proper hover styles on drag handles', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector
          columns={mockColumns}
          onToggle={mockOnToggle}
          onReorder={mockOnReorder}
        />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const dragHandle = container.querySelector('.cursor-move')
        expect(dragHandle).toHaveClass('hover:bg-zinc-200')
        expect(dragHandle).toHaveClass('dark:hover:bg-zinc-700')
      })
    })

    it('should display columns when onReorder is not provided', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByText('Title')).toBeInTheDocument()
      })
    })
  })

  describe('Reset Functionality', () => {
    it('should display reset button when onReset is provided', async () => {
      const user = userEvent.setup()
      render(
        <ColumnSelector
          columns={mockColumns}
          onToggle={mockOnToggle}
          onReset={mockOnReset}
        />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByText('Reset to Default')).toBeInTheDocument()
      })
    })

    it('should not display reset button when onReset is not provided', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        expect(
          screen.queryByRole('button', { name: /reset to default/i })
        ).not.toBeInTheDocument()
      })
    })

    it('should call onReset when reset button clicked', async () => {
      const user = userEvent.setup()
      render(
        <ColumnSelector
          columns={mockColumns}
          onToggle={mockOnToggle}
          onReset={mockOnReset}
        />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(async () => {
        const resetButton = screen.getByText('Reset to Default')
        await user.click(resetButton)
      })

      await waitFor(() => {
        expect(mockOnReset).toHaveBeenCalledTimes(1)
      })
    })

    it('should have proper styling on reset button', async () => {
      const user = userEvent.setup()
      render(
        <ColumnSelector
          columns={mockColumns}
          onToggle={mockOnToggle}
          onReset={mockOnReset}
        />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const resetButton = screen.getByText('Reset to Default')
        expect(resetButton).toHaveClass('hover:bg-zinc-50')
        expect(resetButton).toHaveClass('dark:hover:bg-zinc-800')
      })
    })
  })

  describe('Styling and Layout', () => {
    it('should have proper menu styling', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const menu = container.querySelector('.rounded-lg')
        expect(menu).toBeInTheDocument()
      })
    })

    it('should have scrollable area for columns', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const scrollArea = container.querySelector('.max-h-96')
        expect(scrollArea).toBeInTheDocument()
        expect(scrollArea).toHaveClass('overflow-y-auto')
      })
    })

    it('should have custom scrollbar classes', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const scrollArea = container.querySelector('.scrollbar-thin')
        expect(scrollArea).toBeInTheDocument()
      })
    })

    it('should have proper dark mode classes', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const menu = container.querySelector('.dark\\:bg-zinc-900')
        expect(menu).toBeInTheDocument()
      })
    })

    it('should have proper row hover effects', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const row = screen.getByText('Title').closest('.group')
        expect(row).toHaveClass('hover:bg-zinc-50')
        expect(row).toHaveClass('dark:hover:bg-zinc-800')
      })
    })

    it('should have border between header and content', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const header = screen
          .getByText('Show/Hide & Reorder Columns')
          .closest('div')
        expect(header).toHaveClass('border-b')
      })
    })
  })

  describe('Accessibility', () => {
    it('should have proper button role', () => {
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)
      expect(
        screen.getByRole('button', { name: /columns/i })
      ).toBeInTheDocument()
    })

    it('should have checkboxes with proper role', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const checkboxes = container.querySelectorAll('input[type="checkbox"]')
        expect(checkboxes.length).toBeGreaterThan(0)
      })
    })

    it('should have readonly checkboxes', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const checkbox = container.querySelector('input[type="checkbox"]')
        expect(checkbox).toHaveAttribute('readOnly')
      })
    })

    it('should have pointer-events-none on checkboxes', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const checkbox = container.querySelector('input[type="checkbox"]')
        expect(checkbox).toHaveClass('pointer-events-none')
      })
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty column list', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={[]} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        expect(
          screen.getByText('Show/Hide & Reorder Columns')
        ).toBeInTheDocument()
      })
    })

    it('should handle single column', async () => {
      const user = userEvent.setup()
      const singleColumn = [mockColumns[0]]
      render(<ColumnSelector columns={singleColumn} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        expect(
          screen.getByText('Show/Hide & Reorder Columns')
        ).toBeInTheDocument()
      })
    })

    it('should handle columns without type', async () => {
      const user = userEvent.setup()
      const columnsWithoutType = [
        { id: 'test', label: 'Test', visible: true, sortable: true },
      ]
      render(
        <ColumnSelector columns={columnsWithoutType} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        expect(screen.getByText('Test')).toBeInTheDocument()
      })
    })

    it('should handle very long column labels', async () => {
      const user = userEvent.setup()
      const longLabelColumns = [
        {
          id: 'long',
          label: 'A'.repeat(100),
          visible: true,
          sortable: true,
          type: 'data' as const,
        },
      ]
      render(
        <ColumnSelector columns={longLabelColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const label = screen.getByText('A'.repeat(100))
        expect(label).toHaveClass('truncate')
      })
    })

    it('should handle all columns visible', async () => {
      const user = userEvent.setup()
      const visibleColumns = mockColumns.map((col) => ({
        ...col,
        visible: true,
      }))
      const { container } = render(
        <ColumnSelector columns={visibleColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const checkboxes = container.querySelectorAll('input[type="checkbox"]')
        expect(checkboxes.length).toBeGreaterThan(0)
      })
    })

    it('should handle rapid toggling', async () => {
      const user = userEvent.setup()
      render(<ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />)

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(async () => {
        const titleButton = screen.getByText('Title').closest('button')
        await user.click(titleButton!)
        await user.click(titleButton!)
        expect(mockOnToggle).toHaveBeenCalledTimes(2)
      })
    })
  })

  describe('Menu Positioning', () => {
    it('should have absolute positioning', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const menu = container.querySelector('.absolute')
        expect(menu).toBeInTheDocument()
      })
    })

    it('should have proper z-index', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const menu = container.querySelector('.z-50')
        expect(menu).toBeInTheDocument()
      })
    })

    it('should be positioned left aligned', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const menu = container.querySelector('.left-0')
        expect(menu).toBeInTheDocument()
      })
    })

    it('should have origin-top-left for transforms', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <ColumnSelector columns={mockColumns} onToggle={mockOnToggle} />
      )

      const button = screen.getByRole('button', { name: /columns/i })
      await user.click(button)

      await waitFor(() => {
        const menu = container.querySelector('.origin-top-left')
        expect(menu).toBeInTheDocument()
      })
    })
  })
})
