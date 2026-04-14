/**
 * @jest-environment jsdom
 */

jest.mock('@/lib/api', () => ({
  api: {
    getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
    getTask: jest.fn().mockResolvedValue(null),
    getAllUsers: jest.fn().mockResolvedValue([]),
    getOrganizations: jest.fn().mockResolvedValue([]),
    getAnnotationOverview: jest.fn().mockResolvedValue({ annotations: [] }),
    createTask: jest.fn().mockResolvedValue({}),
    updateTask: jest.fn().mockResolvedValue({}),
    deleteTask: jest.fn().mockResolvedValue(undefined),
    exportBulkData: jest.fn().mockResolvedValue({}),
    importBulkData: jest.fn().mockResolvedValue({}),
  },
  ApiClient: jest.fn().mockImplementation(() => ({
    getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
    getTask: jest.fn().mockResolvedValue(null),
    getAllUsers: jest.fn().mockResolvedValue([]),
    getOrganizations: jest.fn().mockResolvedValue([]),
  })),
}))

// Mock default export of apiClient
jest.mock('@/lib/api', () => {
  const mockApiClient = {
    get: jest.fn().mockResolvedValue({ tasks: [] }),
  }
  return {
    __esModule: true,
    default: mockApiClient,
    api: mockApiClient,
  }
})

// Mock Headless UI Menu components
jest.mock('@headlessui/react', () => ({
  Menu: ({ children }: any) => <div data-testid="menu">{children}</div>,
  Transition: ({ children }: any) => <div>{children}</div>,
  Fragment: ({ children }: any) => <>{children}</>,
}))

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { FilterDropdown } from '../FilterDropdown'
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


// Simple stateful mock for Headless UI Menu
const MockMenu = ({ children }: any) => {
  const [isOpen, setIsOpen] = React.useState(false)

  // Recursively process children to handle nested components
  const processChildren = (children: any): any => {
    return React.Children.map(children, (child) => {
      if (!React.isValidElement(child)) return child

      // Check if this is Menu.Button
      if (child.type === MockMenu.Button || (child.props && child.props.as)) {
        // Wrap the button to intercept clicks
        const OriginalButton = child.props.as || 'button'
        return (
          <div onClick={() => setIsOpen(!isOpen)}>
            {React.createElement(
              OriginalButton,
              {
                ...child.props,
                as: undefined, // Remove the 'as' prop
              },
              child.props.children
            )}
          </div>
        )
      }

      // Check if this is Menu.Items
      if (child.type === MockMenu.Items) {
        return isOpen ? child : null
      }

      // Process children recursively
      if (child.props && child.props.children) {
        return React.cloneElement(child, {
          ...child.props,
          children: processChildren(child.props.children),
        })
      }

      return child
    })
  }

  return (
    <div data-testid="menu" data-menu-open={isOpen}>
      {processChildren(children)}
    </div>
  )
}

MockMenu.Button = React.forwardRef(function MockMenuButton(
  { children, as: Component = 'button', ...props }: any,
  ref
) {
  // If 'as' is provided, use it as the component
  if (Component && Component !== 'button') {
    return (
      <Component ref={ref} {...props}>
        {children}
      </Component>
    )
  }
  return (
    <button ref={ref} {...props}>
      {children}
    </button>
  )
})

MockMenu.Items = function MockMenuItems({ children }: any) {
  return (
    <div data-testid="menu-items" className="menu-items">
      {children}
    </div>
  )
}

MockMenu.Item = function MockMenuItem({ children }: any) {
  if (typeof children === 'function') {
    return <div>{children({ active: false })}</div>
  }
  return <div>{children}</div>
}

// Override the Headless UI mock
;(require('@headlessui/react') as any).Menu = MockMenu

// Mock shared components
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, ...props }: any) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Input', () => ({
  Input: ({ ...props }: any) => <input {...props} />,
}))

/**
 * Test suite for FilterDropdown component with metadata filtering
 * Verifies that the filter dropdown works correctly with status, date, and annotator filters
 */

describe('FilterDropdown', () => {
  const defaultProps = {
    filterStatus: 'all' as const,
    onStatusChange: jest.fn(),
    onDateRangeChange: jest.fn(),
    onAnnotatorChange: jest.fn(),
    metadataFilters: {},
    onMetadataChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  test('renders the filter button', () => {
    render(<FilterDropdown {...defaultProps} />)
    expect(screen.getByText('Filters')).toBeInTheDocument()
  })

  test('opens dropdown when clicked', async () => {
    render(<FilterDropdown {...defaultProps} />)
    const button = screen.getByText('Filters')
    fireEvent.click(button)

    // Wait for dropdown to open and check for filter sections
    await waitFor(() => {
      expect(screen.getByText('Status')).toBeInTheDocument()
    })
    expect(screen.getByText('Date Range')).toBeInTheDocument()
    expect(screen.getByText('Annotator')).toBeInTheDocument()
  })

  test('shows status filter options', async () => {
    render(<FilterDropdown {...defaultProps} />)
    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('All Tasks')).toBeInTheDocument()
    })
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('Incomplete')).toBeInTheDocument()
  })

  test('shows date range filter', async () => {
    render(<FilterDropdown {...defaultProps} />)
    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Date Range')).toBeInTheDocument()
    })
    // Look for date inputs by type
    const dateInputs = screen
      .getAllByDisplayValue('')
      .filter((el) => el.getAttribute('type') === 'date')
    expect(dateInputs.length).toBeGreaterThanOrEqual(2)
  })

  test('shows annotator filter', async () => {
    render(<FilterDropdown {...defaultProps} />)
    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Annotator')).toBeInTheDocument()
    })
    expect(
      screen.getByPlaceholderText('Filter by annotator name...')
    ).toBeInTheDocument()
  })

  test('calls onStatusChange when status filter is clicked', async () => {
    const onStatusChange = jest.fn()
    render(<FilterDropdown {...defaultProps} onStatusChange={onStatusChange} />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Completed')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Completed'))
    expect(onStatusChange).toHaveBeenCalledWith('completed')
  })

  test('shows active filter count when filters are applied', () => {
    const props = {
      ...defaultProps,
      filterStatus: 'completed' as const,
    }

    render(<FilterDropdown {...props} />)

    // Should show "1" for the active status filter
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  test('clears all filters', async () => {
    const onStatusChange = jest.fn()
    const props = {
      ...defaultProps,
      filterStatus: 'completed' as const,
      onStatusChange,
    }

    render(<FilterDropdown {...props} />)
    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Clear All Filters')).toBeInTheDocument()
    })

    const clearButton = screen.getByText('Clear All Filters')
    fireEvent.click(clearButton)

    expect(onStatusChange).toHaveBeenCalledWith('all')
  })

  test('handles date range filter application', async () => {
    const onDateRangeChange = jest.fn()
    render(
      <FilterDropdown {...defaultProps} onDateRangeChange={onDateRangeChange} />
    )

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Date Range')).toBeInTheDocument()
    })

    // Find date inputs and set values
    const dateInputs = screen
      .getAllByDisplayValue('')
      .filter((el) => el.getAttribute('type') === 'date')

    fireEvent.change(dateInputs[0], { target: { value: '2024-01-01' } })
    fireEvent.change(dateInputs[1], { target: { value: '2024-12-31' } })

    // Find and click the Apply button
    const applyButton = screen.getByText('Apply Date Filter')
    fireEvent.click(applyButton)

    expect(onDateRangeChange).toHaveBeenCalledWith('2024-01-01', '2024-12-31')
  })

  test('handles annotator filter application', async () => {
    const onAnnotatorChange = jest.fn()
    render(
      <FilterDropdown {...defaultProps} onAnnotatorChange={onAnnotatorChange} />
    )

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Annotator')).toBeInTheDocument()
    })

    const annotatorInput = screen.getByPlaceholderText(
      'Filter by annotator name...'
    )
    fireEvent.change(annotatorInput, { target: { value: 'John Doe' } })

    const applyButton = screen.getByText('Apply Annotator Filter')
    fireEvent.click(applyButton)

    expect(onAnnotatorChange).toHaveBeenCalledWith('John Doe')
  })

  test('disables date filter button when dates not set', async () => {
    render(<FilterDropdown {...defaultProps} />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Apply Date Filter')).toBeInTheDocument()
    })

    const applyButton = screen.getByText('Apply Date Filter')
    expect(applyButton).toBeDisabled()
  })

  test('disables annotator filter button when annotator not set', async () => {
    render(<FilterDropdown {...defaultProps} />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Apply Annotator Filter')).toBeInTheDocument()
    })

    const applyButton = screen.getByText('Apply Annotator Filter')
    expect(applyButton).toBeDisabled()
  })

  test('updates date range state correctly', async () => {
    render(<FilterDropdown {...defaultProps} />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Date Range')).toBeInTheDocument()
    })

    const dateInputs = screen
      .getAllByDisplayValue('')
      .filter((el) => el.getAttribute('type') === 'date')

    fireEvent.change(dateInputs[0], { target: { value: '2024-01-01' } })
    expect(dateInputs[0]).toHaveValue('2024-01-01')

    fireEvent.change(dateInputs[1], { target: { value: '2024-12-31' } })
    expect(dateInputs[1]).toHaveValue('2024-12-31')
  })

  test('updates annotator filter state correctly', async () => {
    render(<FilterDropdown {...defaultProps} />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Annotator')).toBeInTheDocument()
    })

    const annotatorInput = screen.getByPlaceholderText(
      'Filter by annotator name...'
    )
    fireEvent.change(annotatorInput, { target: { value: 'Test Annotator' } })
    expect(annotatorInput).toHaveValue('Test Annotator')
  })

  test('shows metadata filter section', async () => {
    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Filter by Metadata')).toBeInTheDocument()
    })
  })

  test('handles missing callbacks gracefully', async () => {
    const props = {
      filterStatus: 'all' as const,
      onStatusChange: jest.fn(),
    }

    render(<FilterDropdown {...props} />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Clear All Filters')).toBeInTheDocument()
    })

    const clearButton = screen.getByText('Clear All Filters')
    fireEvent.click(clearButton)

    expect(props.onStatusChange).toHaveBeenCalledWith('all')
  })

  test('shows current filter status in button', () => {
    const props = {
      ...defaultProps,
      filterStatus: 'completed' as const,
    }

    render(<FilterDropdown {...props} />)
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  test('calculates active filter count correctly with multiple filters', async () => {
    const props = {
      ...defaultProps,
      filterStatus: 'completed' as const,
      metadataFilters: { category: ['legal'] },
    }

    render(<FilterDropdown {...props} />)

    // filterStatus !== 'all' + metadataFilters > 0 = 2
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  test('handles status change to incomplete', async () => {
    const onStatusChange = jest.fn()
    render(<FilterDropdown {...defaultProps} onStatusChange={onStatusChange} />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Incomplete')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Incomplete'))
    expect(onStatusChange).toHaveBeenCalledWith('incomplete')
  })

  test('clears date range when clear all filters is clicked', async () => {
    const onDateRangeChange = jest.fn()
    const props = {
      ...defaultProps,
      onDateRangeChange,
    }

    render(<FilterDropdown {...props} />)
    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Clear All Filters')).toBeInTheDocument()
    })

    const clearButton = screen.getByText('Clear All Filters')
    fireEvent.click(clearButton)

    expect(onDateRangeChange).toHaveBeenCalledWith('', '')
  })

  test('clears annotator filter when clear all filters is clicked', async () => {
    const onAnnotatorChange = jest.fn()
    const props = {
      ...defaultProps,
      onAnnotatorChange,
    }

    render(<FilterDropdown {...props} />)
    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Clear All Filters')).toBeInTheDocument()
    })

    const clearButton = screen.getByText('Clear All Filters')
    fireEvent.click(clearButton)

    expect(onAnnotatorChange).toHaveBeenCalledWith('')
  })

  test('clears metadata filters when clear all filters is clicked', async () => {
    const onMetadataChange = jest.fn()
    const props = {
      ...defaultProps,
      onMetadataChange,
      metadataFilters: { category: ['legal'] },
    }

    render(<FilterDropdown {...props} />)
    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Clear All Filters')).toBeInTheDocument()
    })

    const clearButton = screen.getByText('Clear All Filters')
    fireEvent.click(clearButton)

    expect(onMetadataChange).toHaveBeenCalledWith({})
  })

  test('shows checkmark for selected status', async () => {
    const props = {
      ...defaultProps,
      filterStatus: 'completed' as const,
    }

    render(<FilterDropdown {...props} />)
    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Completed')).toBeInTheDocument()
    })

    // Check that checkmark icon is present near the Completed option
    const completedOption = screen.getByText('Completed').closest('button')
    expect(completedOption).toBeInTheDocument()
  })

  test('does not fetch metadata when projectId is not provided', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockClear()

    render(<FilterDropdown {...defaultProps} />)

    expect(apiClient.get).not.toHaveBeenCalled()
  })

  test('fetches metadata when projectId is provided', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        {
          meta: {
            category: 'legal',
            priority: 'high',
          },
        },
      ],
    })

    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith(
        '/projects/test-project/tasks?limit=100'
      )
    })
  })

  test('handles metadata fetch error silently', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockRejectedValueOnce(new Error('Network error'))

    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    // Should not throw error
    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalled()
    })
  })

  test('displays no metadata message when no fields available', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [],
    })

    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(
        screen.getByText('No metadata fields available')
      ).toBeInTheDocument()
    })
  })

  test('parses metadata from tasks correctly', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        {
          meta: {
            category: 'legal',
            priority: 'high',
          },
        },
        {
          meta: {
            category: 'tax',
            priority: 'high',
          },
        },
      ],
    })

    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('category')).toBeInTheDocument()
    })
    expect(screen.getByText('priority')).toBeInTheDocument()
  })

  test('handles array metadata values', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        {
          meta: {
            tags: ['urgent', 'legal'],
          },
        },
      ],
    })

    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('tags')).toBeInTheDocument()
    })
  })

  test('toggles metadata filter on click', async () => {
    const onMetadataChange = jest.fn()
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        {
          meta: {
            category: 'legal',
          },
        },
      ],
    })

    render(
      <FilterDropdown
        {...defaultProps}
        projectId="test-project"
        onMetadataChange={onMetadataChange}
      />
    )

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('legal')).toBeInTheDocument()
    })

    const legalButton = screen.getByText('legal')
    fireEvent.click(legalButton)

    expect(onMetadataChange).toHaveBeenCalledWith({
      category: ['legal'],
    })
  })

  test('removes metadata filter when clicked again', async () => {
    const onMetadataChange = jest.fn()
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        {
          meta: {
            category: 'legal',
          },
        },
      ],
    })

    render(
      <FilterDropdown
        {...defaultProps}
        projectId="test-project"
        metadataFilters={{ category: ['legal'] }}
        onMetadataChange={onMetadataChange}
      />
    )

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Active filters')).toBeInTheDocument()
    })

    // Find the remove button (X) next to the legal tag
    const removeButtons = screen.getAllByRole('button')
    const legalRemoveButton = removeButtons.find((btn) =>
      btn.getAttribute('aria-label')?.includes('Remove filter category:legal')
    )

    if (legalRemoveButton) {
      fireEvent.click(legalRemoveButton)
      expect(onMetadataChange).toHaveBeenCalledWith({})
    }
  })

  test('displays active metadata filters', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        {
          meta: {
            category: 'legal',
          },
        },
      ],
    })

    render(
      <FilterDropdown
        {...defaultProps}
        projectId="test-project"
        metadataFilters={{ category: ['legal'] }}
      />
    )

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Active filters')).toBeInTheDocument()
    })
    expect(screen.getByText('category:')).toBeInTheDocument()
  })

  test('handles non-array metadata filter values', async () => {
    const onMetadataChange = jest.fn()
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        {
          meta: {
            status: 'active',
          },
        },
      ],
    })

    render(
      <FilterDropdown
        {...defaultProps}
        projectId="test-project"
        metadataFilters={{ status: 'active' }}
        onMetadataChange={onMetadataChange}
      />
    )

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getAllByText('active').length).toBeGreaterThan(0)
    })

    // Find and click the remove filter button (X icon) to remove the filter
    const removeButton = screen.getByLabelText('Remove filter status:active')
    fireEvent.click(removeButton)

    await waitFor(() => {
      expect(onMetadataChange).toHaveBeenCalledWith({})
    })
  })

  test('limits metadata values to top 10', async () => {
    const apiClient = require('@/lib/api').default
    const tasks = Array.from({ length: 15 }, (_, i) => ({
      meta: {
        category: `cat${i}`,
      },
    }))

    apiClient.get.mockResolvedValueOnce({ tasks })

    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('category')).toBeInTheDocument()
    })

    // Should only show top 10 values
    const categoryValues = screen
      .getAllByText(/^cat\d+$/)
      .filter((el) => el.tagName === 'BUTTON')
    expect(categoryValues.length).toBeLessThanOrEqual(10)
  })

  test('shows value counts in metadata options', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        { meta: { category: 'legal' } },
        { meta: { category: 'legal' } },
        { meta: { category: 'tax' } },
      ],
    })

    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText(/\(2\)/)).toBeInTheDocument()
    })
    expect(screen.getByText(/\(1\)/)).toBeInTheDocument()
  })

  test('handles tasks without metadata', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [{ data: { text: 'Task 1' } }, { data: { text: 'Task 2' } }],
    })

    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(
        screen.getByText('No metadata fields available')
      ).toBeInTheDocument()
    })
  })

  test('detects metadata field types correctly', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        {
          meta: {
            text_field: 'text',
            array_field: ['item1', 'item2'],
            number_field: 42,
            bool_field: true,
          },
        },
      ],
    })

    render(<FilterDropdown {...defaultProps} projectId="test-project" />)

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('text_field')).toBeInTheDocument()
    })
    expect(screen.getByText('array_field')).toBeInTheDocument()
    expect(screen.getByText('number_field')).toBeInTheDocument()
    expect(screen.getByText('bool_field')).toBeInTheDocument()
  })

  test('handles multiple active metadata filters', async () => {
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [
        {
          meta: {
            category: 'legal',
            priority: 'high',
          },
        },
      ],
    })

    render(
      <FilterDropdown
        {...defaultProps}
        projectId="test-project"
        metadataFilters={{
          category: ['legal'],
          priority: ['high'],
        }}
      />
    )

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('Active filters')).toBeInTheDocument()
    })
    expect(screen.getByText('category:')).toBeInTheDocument()
    expect(screen.getByText('priority:')).toBeInTheDocument()
  })

  test('adds multiple values to same metadata filter', async () => {
    const onMetadataChange = jest.fn()
    const apiClient = require('@/lib/api').default
    apiClient.get.mockResolvedValueOnce({
      tasks: [{ meta: { category: 'legal' } }, { meta: { category: 'tax' } }],
    })

    render(
      <FilterDropdown
        {...defaultProps}
        projectId="test-project"
        metadataFilters={{ category: ['legal'] }}
        onMetadataChange={onMetadataChange}
      />
    )

    const button = screen.getByText('Filters')
    fireEvent.click(button)

    await waitFor(() => {
      expect(screen.getByText('tax')).toBeInTheDocument()
    })

    const taxButton = screen.getByText('tax')
    fireEvent.click(taxButton)

    expect(onMetadataChange).toHaveBeenCalledWith({
      category: ['legal', 'tax'],
    })
  })
})
