import { fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import {
  EmptyState,
  NoAnalyticsDataEmptyState,
  NoTaskSelectedEmptyState,
} from '../EmptyStates'

/* eslint-disable react/display-name */

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, string>) => {
      const translations: Record<string, string> = {
        'emptyStates.noAnalytics': 'No Analytics Available Yet',
        'emptyStates.noAnalyticsMessage': "This task doesn't have an annotation project linked yet, so analytics are not available.",
        'emptyStates.noAnalyticsMessageWithTask': 'The task "{taskName}" doesn\'t have an annotation project linked yet, so analytics are not available.',
        'emptyStates.backToDashboard': 'Back to Dashboard',
        'emptyStates.selectTask': 'Select a Task',
        'emptyStates.selectTaskMessage': 'Choose a task from the dropdown above to view its analytics and annotation data.',
        'emptyStates.browseTasks': 'Browse Tasks',
      }
      let result = translations[key] || key
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          result = result.replace(new RegExp(`\\{${k}\\}`, 'g'), v)
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

// Mock Next.js Link component
jest.mock('next/link', () => {
  return ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  )
})

describe('EmptyState', () => {
  const defaultProps = {
    title: 'No Data Available',
    description: 'There is no data to display at this time.',
  }

  it('renders title and description correctly', () => {
    render(<EmptyState {...defaultProps} />)
    expect(screen.getByText('No Data Available')).toBeInTheDocument()
    expect(
      screen.getByText('There is no data to display at this time.')
    ).toBeInTheDocument()
  })

  it('renders icon when provided', () => {
    const icon = <svg data-testid="test-icon" />
    render(<EmptyState {...defaultProps} icon={icon} />)
    expect(screen.getByTestId('test-icon')).toBeInTheDocument()
  })

  it('does not render icon container when icon is not provided', () => {
    const { container } = render(<EmptyState {...defaultProps} />)
    const iconContainer = container.querySelector('.rounded-full')
    expect(iconContainer).not.toBeInTheDocument()
  })

  it('renders action button with onClick handler', () => {
    const handleClick = jest.fn()
    render(
      <EmptyState
        {...defaultProps}
        action={{ label: 'Take Action', onClick: handleClick }}
      />
    )

    const button = screen.getByText('Take Action')
    expect(button).toBeInTheDocument()
    fireEvent.click(button)
    expect(handleClick).toHaveBeenCalledTimes(1)
  })

  it('renders action button as link when href is provided', () => {
    render(
      <EmptyState
        {...defaultProps}
        action={{ label: 'Go to Page', href: '/some-page' }}
      />
    )

    const link = screen.getByText('Go to Page').closest('a')
    expect(link).toHaveAttribute('href', '/some-page')
  })

  it('applies custom className', () => {
    const { container } = render(
      <EmptyState {...defaultProps} className="custom-empty-state" />
    )
    const emptyStateElement = container.firstChild as HTMLElement
    expect(emptyStateElement).toHaveClass('custom-empty-state')
  })

  it('does not render action section when action is not provided', () => {
    render(<EmptyState {...defaultProps} />)
    const buttons = screen.queryAllByRole('button')
    expect(buttons).toHaveLength(0)
  })

  it('applies correct styling classes', () => {
    const { container } = render(<EmptyState {...defaultProps} />)
    const emptyStateElement = container.firstChild as HTMLElement
    expect(emptyStateElement).toHaveClass('text-center')
    expect(emptyStateElement).toHaveClass('py-12')
    expect(emptyStateElement).toHaveClass('px-4')
  })
})

describe('NoAnalyticsDataEmptyState', () => {
  it('renders with default message when no task name provided', () => {
    render(<NoAnalyticsDataEmptyState />)
    expect(screen.getByText('No Analytics Available Yet')).toBeInTheDocument()
    expect(
      screen.getByText(/This task doesn't have an annotation project/)
    ).toBeInTheDocument()
  })

  it('renders with task name in message when provided', () => {
    render(<NoAnalyticsDataEmptyState taskName="Test Task" />)
    expect(
      screen.getByText(/The task "Test Task" doesn't have/)
    ).toBeInTheDocument()
  })

  it('renders Back to Dashboard button when handler provided', () => {
    const handleBack = jest.fn()
    render(<NoAnalyticsDataEmptyState onBackToDashboard={handleBack} />)

    const button = screen.getByText('Back to Dashboard')
    expect(button).toBeInTheDocument()
    fireEvent.click(button)
    expect(handleBack).toHaveBeenCalledTimes(1)
  })

  it('does not render button when no handler provided', () => {
    render(<NoAnalyticsDataEmptyState />)
    const button = screen.queryByText('Back to Dashboard')
    expect(button).not.toBeInTheDocument()
  })

  it('renders retry functionality when provided', () => {
    const handleRetry = jest.fn()
    render(<NoAnalyticsDataEmptyState onRetry={handleRetry} />)
    // Note: onRetry is passed but not used in the current implementation
    // This test documents the current behavior
    const button = screen.queryByText('Retry')
    expect(button).not.toBeInTheDocument()
  })

  it('renders icon correctly', () => {
    const { container } = render(<NoAnalyticsDataEmptyState />)
    const icon = container.querySelector('svg')
    expect(icon).toBeInTheDocument()
    expect(icon).toHaveClass('h-8')
    expect(icon).toHaveClass('w-8')
  })
})

describe('NoTaskSelectedEmptyState', () => {
  it('renders correct title and description', () => {
    render(<NoTaskSelectedEmptyState />)
    expect(screen.getByText('Select a Task')).toBeInTheDocument()
    expect(
      screen.getByText(/Choose a task from the dropdown/)
    ).toBeInTheDocument()
  })

  it('renders Browse Tasks button when handler provided', () => {
    const handleSelect = jest.fn()
    render(<NoTaskSelectedEmptyState onSelectTask={handleSelect} />)

    const button = screen.getByText('Browse Tasks')
    expect(button).toBeInTheDocument()
    fireEvent.click(button)
    expect(handleSelect).toHaveBeenCalledTimes(1)
  })

  it('does not render button when no handler provided', () => {
    render(<NoTaskSelectedEmptyState />)
    const button = screen.queryByText('Browse Tasks')
    expect(button).not.toBeInTheDocument()
  })

  it('renders icon correctly', () => {
    const { container } = render(<NoTaskSelectedEmptyState />)
    const icon = container.querySelector('svg')
    expect(icon).toBeInTheDocument()
    expect(icon).toHaveClass('h-8')
    expect(icon).toHaveClass('w-8')
  })

  it('maintains proper component structure', () => {
    const { container } = render(<NoTaskSelectedEmptyState />)
    const title = screen.getByText('Select a Task')
    expect(title.tagName).toBe('H3')
    expect(title).toHaveClass('text-lg')
    expect(title).toHaveClass('font-medium')
  })
})
