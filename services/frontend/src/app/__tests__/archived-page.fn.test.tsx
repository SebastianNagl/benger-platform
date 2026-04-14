/**
 * Coverage for projects/archived/page.tsx (0% -> 100%)
 */

import { render, screen } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: string) => fallback || key,
    locale: 'en',
  }),
}))

jest.mock('@/components/projects/ProjectListTable', () => ({
  ProjectListTable: ({ showArchivedOnly }: any) => (
    <div data-testid="project-list" data-archived={showArchivedOnly}>
      Project List
    </div>
  ),
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))

jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children, size, className }: any) => (
    <div data-testid="container" data-size={size} className={className}>
      {children}
    </div>
  ),
}))

import ArchivedProjectsPage from '../projects/archived/page'

describe('ArchivedProjectsPage', () => {
  it('renders with breadcrumb', () => {
    render(<ArchivedProjectsPage />)
    expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
  })

  it('renders project list table with archived filter', () => {
    render(<ArchivedProjectsPage />)
    const table = screen.getByTestId('project-list')
    expect(table).toHaveAttribute('data-archived', 'true')
  })

  it('uses full size responsive container', () => {
    render(<ArchivedProjectsPage />)
    const container = screen.getByTestId('container')
    expect(container).toHaveAttribute('data-size', 'full')
  })
})
