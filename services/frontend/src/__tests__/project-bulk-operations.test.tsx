/**
 * @jest-environment jsdom
 */

import { ProjectBulkActions } from '@/components/projects/ProjectBulkActions'
import { TableCheckbox } from '@/components/projects/TableCheckbox'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'

// Mock the custom Toast component
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({
    addToast: mockAddToast,
  }),
  ToastProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}))

// Mock dependencies
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    bulkDelete: jest.fn(),
    bulkDeleteProjects: jest.fn(),
    bulkExport: jest.fn(),
    bulkExportProjects: jest.fn(),
    bulkArchive: jest.fn(),
    bulkArchiveProjects: jest.fn(),
    bulkUnarchive: jest.fn(),
    bulkDuplicate: jest.fn(),
  },
}))

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
    route: '/',
    basePath: '',
    isReady: true,
    isPreview: false,
    isLocaleDomain: false,
  })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn(),
}))

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href, ...props }: any) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

const mockProjects = [
  {
    id: '1',
    title: 'Test Project 1',
    description: 'Description 1',
    task_count: 10,
    annotation_count: 5,
    is_archived: false,
    created_at: '2024-01-01',
    updated_at: '2024-01-02',
  },
  {
    id: '2',
    title: 'Test Project 2',
    description: 'Description 2',
    task_count: 20,
    annotation_count: 15,
    is_archived: false,
    created_at: '2024-01-03',
    updated_at: '2024-01-04',
  },
  {
    id: '3',
    title: 'Test Project 3',
    description: 'Description 3',
    task_count: 30,
    annotation_count: 25,
    is_archived: true,
    created_at: '2024-01-05',
    updated_at: '2024-01-06',
  },
]

// Mock stores
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    projects: mockProjects,
    fetchProjects: jest.fn(),
    loading: false,
    error: null,
    searchQuery: '',
    setSearchQuery: jest.fn(),
  }),
}))

describe('ProjectBulkActions', () => {
  const mockOnDelete = jest.fn()
  const mockOnExport = jest.fn()
  const mockOnArchive = jest.fn()
  const mockOnDuplicate = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders bulk actions dropdown with correct count', async () => {
    render(
      <ProjectBulkActions
        selectedCount={2}
        onDelete={mockOnDelete}
        onExport={mockOnExport}
        onArchive={mockOnArchive}
        onDuplicate={mockOnDuplicate}
      />
    )

    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('Actions')).toBeInTheDocument()
  })

  it('disables dropdown when no projects are selected', async () => {
    render(
      <ProjectBulkActions
        selectedCount={0}
        onDelete={mockOnDelete}
        onExport={mockOnExport}
        onArchive={mockOnArchive}
        onDuplicate={mockOnDuplicate}
      />
    )

    const button = screen.getByText('Actions')
    expect(button.closest('button')).toBeDisabled()
  })

  it('calls delete handler when delete option is clicked', async () => {
    const user = userEvent.setup()

    render(
      <ProjectBulkActions
        selectedCount={2}
        onDelete={mockOnDelete}
        onExport={mockOnExport}
        onArchive={mockOnArchive}
        onDuplicate={mockOnDuplicate}
      />
    )

    // Open dropdown
    await user.click(screen.getByText('Actions'))

    // Click delete option
    await user.click(screen.getByText('Delete Selected'))

    expect(mockOnDelete).toHaveBeenCalledTimes(1)
  })

  it('calls export handler when export option is clicked', async () => {
    const user = userEvent.setup()

    render(
      <ProjectBulkActions
        selectedCount={1}
        onDelete={mockOnDelete}
        onFullExport={mockOnExport}
        onArchive={mockOnArchive}
        onDuplicate={mockOnDuplicate}
      />
    )

    await user.click(screen.getByText('Actions'))
    await user.click(screen.getByText('Export Selected Projects'))

    expect(mockOnExport).toHaveBeenCalledTimes(1)
  })

  it('calls archive handler when archive option is clicked', async () => {
    const user = userEvent.setup()

    render(
      <ProjectBulkActions
        selectedCount={3}
        onDelete={mockOnDelete}
        onExport={mockOnExport}
        onArchive={mockOnArchive}
        onDuplicate={mockOnDuplicate}
      />
    )

    await user.click(screen.getByText('Actions'))
    await user.click(screen.getByText('Archive Selected'))

    expect(mockOnArchive).toHaveBeenCalledTimes(1)
  })
})

describe('TableCheckbox Component', () => {
  it('renders checked state correctly', async () => {
    const onChange = jest.fn()

    render(<TableCheckbox checked={true} onChange={onChange} />)

    const checkbox = screen.getByRole('checkbox')
    expect(checkbox).toBeChecked()
  })

  it('renders indeterminate state correctly', async () => {
    const onChange = jest.fn()
    const { container } = render(
      <TableCheckbox checked={false} indeterminate={true} onChange={onChange} />
    )

    const checkbox = container.querySelector('input[type="checkbox"]')
    expect(checkbox).toHaveProperty('indeterminate', true)
  })

  it('calls onChange when clicked', async () => {
    const user = userEvent.setup()
    const onChange = jest.fn()

    render(<TableCheckbox checked={false} onChange={onChange} />)

    const checkbox = screen.getByRole('checkbox')
    await user.click(checkbox)

    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('respects disabled state', () => {
    const onChange = jest.fn()

    render(
      <TableCheckbox checked={false} onChange={onChange} disabled={true} />
    )

    const checkbox = screen.getByRole('checkbox')
    expect(checkbox).toBeDisabled()
  })
})

// Mock shared components to prevent import errors
jest.mock('@/components/shared', () => {
  const React = require('react')
  return {
    HeroPattern: () =>
      React.createElement(
        'div',
        { 'data-testid': 'hero-pattern' },
        'Hero Pattern'
      ),
  }
})

// Mock i18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../locales/en/common.json')
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
