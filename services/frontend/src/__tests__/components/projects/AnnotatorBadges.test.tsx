/**
 * Unit tests for AnnotatorBadges component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AnnotatorBadges } from '../../../components/projects/AnnotatorBadges'

// Mock Tooltip component
jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({
    children,
    content,
  }: {
    children: React.ReactNode
    content: string
  }) => <div data-tooltip={content}>{children}</div>,
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


describe('AnnotatorBadges', () => {
  const mockAssignments = [
    {
      id: 'assign-1',
      user_id: 'user-1',
      user_name: 'John Doe',
      user_email: 'john@example.com',
      status: 'assigned' as const,
      priority: 1,
    },
    {
      id: 'assign-2',
      user_id: 'user-2',
      user_name: 'Jane Smith',
      user_email: 'jane@example.com',
      status: 'in_progress' as const,
      priority: 2,
    },
    {
      id: 'assign-3',
      user_id: 'user-3',
      user_name: 'Bob Wilson',
      user_email: 'bob@example.com',
      status: 'completed' as const,
      priority: 0,
    },
  ]

  describe('Empty State', () => {
    it('should show unassigned text when no assignments', () => {
      render(<AnnotatorBadges assignments={[]} />)

      expect(screen.getByText('Unassigned')).toBeInTheDocument()
    })

    it('should show assign button when can assign', () => {
      const mockOnAssign = jest.fn()

      render(
        <AnnotatorBadges
          assignments={[]}
          canAssign={true}
          onAssign={mockOnAssign}
        />
      )

      expect(screen.getByText('+ Assign')).toBeInTheDocument()
    })

    it('should call onAssign when assign button is clicked', async () => {
      const user = userEvent.setup()
      const mockOnAssign = jest.fn()

      render(
        <AnnotatorBadges
          assignments={[]}
          canAssign={true}
          onAssign={mockOnAssign}
        />
      )

      const assignButton = screen.getByText('+ Assign')
      await user.click(assignButton)

      expect(mockOnAssign).toHaveBeenCalled()
    })

    it('should not be clickable when cannot assign', () => {
      render(<AnnotatorBadges assignments={[]} canAssign={false} />)

      const unassignedText = screen.getByText('Unassigned')
      expect(unassignedText).not.toHaveClass('cursor-pointer')
    })

    it('should not call onAssign when disabled', async () => {
      const user = userEvent.setup()
      const mockOnAssign = jest.fn()

      render(
        <AnnotatorBadges
          assignments={[]}
          canAssign={false}
          onAssign={mockOnAssign}
        />
      )

      const unassignedButton = screen.getByText('Unassigned')
      await user.click(unassignedButton)

      expect(mockOnAssign).not.toHaveBeenCalled()
    })
  })

  describe('Badge Display', () => {
    it('should render badges for all assignments', () => {
      render(<AnnotatorBadges assignments={mockAssignments} />)

      expect(screen.getByText('JD')).toBeInTheDocument()
      expect(screen.getByText('JS')).toBeInTheDocument()
      expect(screen.getByText('BW')).toBeInTheDocument()
    })

    it('should generate correct initials from names', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'Alice Johnson',
          user_email: 'alice@example.com',
        },
        {
          id: 'a2',
          user_id: 'u2',
          user_name: 'Bob',
          user_email: 'bob@example.com',
        },
      ]

      render(<AnnotatorBadges assignments={assignments} />)

      expect(screen.getByText('AJ')).toBeInTheDocument()
      expect(screen.getByText('BO')).toBeInTheDocument()
    })

    it('should generate initials from email when no name', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_email: 'testuser@example.com',
        },
      ]

      render(<AnnotatorBadges assignments={assignments} />)

      expect(screen.getByText('TE')).toBeInTheDocument()
    })

    it('should show ?? when no name or email', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
        },
      ]

      render(<AnnotatorBadges assignments={assignments} />)

      expect(screen.getByText('??')).toBeInTheDocument()
    })

    it('should handle multi-word names correctly', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'John Michael Smith',
          user_email: 'john@example.com',
        },
      ]

      render(<AnnotatorBadges assignments={assignments} />)

      expect(screen.getByText('JS')).toBeInTheDocument()
    })
  })

  describe('Badge Sizes', () => {
    it('should apply xs size class', () => {
      render(<AnnotatorBadges assignments={mockAssignments} size="xs" />)

      // The text is inside the badge element which has the size classes
      const badge = screen.getByText('JD').closest('.rounded-full')
      expect(badge).toHaveClass('h-5', 'w-5')
    })

    it('should apply sm size class (default)', () => {
      render(<AnnotatorBadges assignments={mockAssignments} />)

      const badge = screen.getByText('JD').closest('.rounded-full')
      expect(badge).toHaveClass('h-6', 'w-6')
    })

    it('should apply md size class', () => {
      render(<AnnotatorBadges assignments={mockAssignments} size="md" />)

      const badge = screen.getByText('JD').closest('.rounded-full')
      expect(badge).toHaveClass('h-8', 'w-8')
    })

    it('should apply lg size class', () => {
      render(<AnnotatorBadges assignments={mockAssignments} size="lg" />)

      const badge = screen.getByText('JD').closest('.rounded-full')
      expect(badge).toHaveClass('h-10', 'w-10')
    })
  })

  describe('Status Indicators', () => {
    it('should show completed status indicator', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'John Doe',
          user_email: 'john@example.com',
          status: 'completed' as const,
        },
      ]

      const { container } = render(
        <AnnotatorBadges assignments={assignments} showStatus={true} />
      )

      const statusIndicator = container.querySelector('.bg-emerald-500')
      expect(statusIndicator).toBeInTheDocument()
    })

    it('should show in_progress status indicator', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'John Doe',
          user_email: 'john@example.com',
          status: 'in_progress' as const,
        },
      ]

      const { container } = render(
        <AnnotatorBadges assignments={assignments} showStatus={true} />
      )

      const statusIndicator = container.querySelector('.bg-yellow-500')
      expect(statusIndicator).toBeInTheDocument()
    })

    it('should show skipped status indicator', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'John Doe',
          user_email: 'john@example.com',
          status: 'skipped' as const,
        },
      ]

      const { container } = render(
        <AnnotatorBadges assignments={assignments} showStatus={true} />
      )

      const statusIndicator = container.querySelector('.bg-zinc-400')
      expect(statusIndicator).toBeInTheDocument()
    })

    it('should not show status indicator when showStatus is false', () => {
      const { container } = render(
        <AnnotatorBadges assignments={mockAssignments} showStatus={false} />
      )

      const statusIndicator = container.querySelector('.bg-emerald-500')
      expect(statusIndicator).not.toBeInTheDocument()
    })

    it('should not show status indicator for assigned status', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'John Doe',
          user_email: 'john@example.com',
          status: 'assigned' as const,
        },
      ]

      const { container } = render(
        <AnnotatorBadges assignments={assignments} showStatus={true} />
      )

      const statusIndicators = container.querySelectorAll(
        '.bg-emerald-500, .bg-yellow-500, .bg-zinc-400'
      )
      expect(statusIndicators).toHaveLength(0)
    })
  })

  describe('Tooltips', () => {
    it('should display user name in tooltip', () => {
      const { container } = render(
        <AnnotatorBadges assignments={mockAssignments} />
      )

      const tooltip = container.querySelector('[data-tooltip*="John Doe"]')
      expect(tooltip).toBeInTheDocument()
    })

    it('should display email when no name', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_email: 'test@example.com',
        },
      ]

      const { container } = render(
        <AnnotatorBadges assignments={assignments} />
      )

      const tooltip = container.querySelector(
        '[data-tooltip*="test@example.com"]'
      )
      expect(tooltip).toBeInTheDocument()
    })

    it('should display status in tooltip', () => {
      const { container } = render(
        <AnnotatorBadges assignments={mockAssignments} />
      )

      const tooltip = container.querySelector('[data-tooltip*="in progress"]')
      expect(tooltip).toBeInTheDocument()
    })

    it('should display priority in tooltip', () => {
      const { container } = render(
        <AnnotatorBadges assignments={mockAssignments} />
      )

      const tooltip = container.querySelector('[data-tooltip*="Priority: 1"]')
      expect(tooltip).toBeInTheDocument()
    })

    it('should not display priority 0 in tooltip', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'John Doe',
          user_email: 'john@example.com',
          priority: 0,
        },
      ]

      const { container } = render(
        <AnnotatorBadges assignments={assignments} />
      )

      const tooltipContent = container
        .querySelector('[data-tooltip]')
        ?.getAttribute('data-tooltip')
      expect(tooltipContent).not.toContain('Priority')
    })
  })

  describe('Unassign Functionality', () => {
    it('should show remove button when canUnassign is true', () => {
      const mockOnUnassign = jest.fn()
      const { container } = render(
        <AnnotatorBadges
          assignments={mockAssignments}
          canUnassign={true}
          onUnassign={mockOnUnassign}
        />
      )

      const removeButtons = container.querySelectorAll(
        '[title="Remove assignment"]'
      )
      expect(removeButtons.length).toBeGreaterThan(0)
    })

    it('should not show remove button when canUnassign is false', () => {
      const { container } = render(
        <AnnotatorBadges assignments={mockAssignments} canUnassign={false} />
      )

      const removeButtons = container.querySelectorAll(
        '[title="Remove assignment"]'
      )
      expect(removeButtons).toHaveLength(0)
    })

    it('should call onUnassign with assignment id', async () => {
      const user = userEvent.setup()
      const mockOnUnassign = jest.fn()
      const { container } = render(
        <AnnotatorBadges
          assignments={mockAssignments}
          canUnassign={true}
          onUnassign={mockOnUnassign}
        />
      )

      const removeButton = container.querySelector(
        '[title="Remove assignment"]'
      ) as HTMLElement
      await user.click(removeButton)

      expect(mockOnUnassign).toHaveBeenCalledWith('assign-1')
    })

    it('should stop event propagation on unassign click', async () => {
      const user = userEvent.setup()
      const mockOnUnassign = jest.fn()
      const mockParentClick = jest.fn()

      const { container } = render(
        <div onClick={mockParentClick}>
          <AnnotatorBadges
            assignments={mockAssignments}
            canUnassign={true}
            onUnassign={mockOnUnassign}
          />
        </div>
      )

      const removeButton = container.querySelector(
        '[title="Remove assignment"]'
      ) as HTMLElement
      await user.click(removeButton)

      expect(mockOnUnassign).toHaveBeenCalled()
      expect(mockParentClick).not.toHaveBeenCalled()
    })
  })

  describe('Max Visible Limit', () => {
    it('should limit visible assignments to maxVisible', () => {
      render(<AnnotatorBadges assignments={mockAssignments} maxVisible={2} />)

      expect(screen.getByText('JD')).toBeInTheDocument()
      expect(screen.getByText('JS')).toBeInTheDocument()
      expect(screen.queryByText('BW')).not.toBeInTheDocument()
    })

    it('should show remaining count badge', () => {
      const manyAssignments = [
        ...mockAssignments,
        {
          id: 'assign-4',
          user_id: 'user-4',
          user_name: 'Charlie Brown',
          user_email: 'charlie@example.com',
        },
        {
          id: 'assign-5',
          user_id: 'user-5',
          user_name: 'Diana Prince',
          user_email: 'diana@example.com',
        },
      ]

      render(<AnnotatorBadges assignments={manyAssignments} maxVisible={3} />)

      expect(screen.getByText('+2')).toBeInTheDocument()
    })

    it('should show all remaining users in tooltip', () => {
      const manyAssignments = [
        ...mockAssignments,
        {
          id: 'assign-4',
          user_id: 'user-4',
          user_name: 'Charlie Brown',
          user_email: 'charlie@example.com',
        },
      ]

      const { container } = render(
        <AnnotatorBadges assignments={manyAssignments} maxVisible={2} />
      )

      const remainingTooltip = container.querySelector(
        '[data-tooltip*="Bob Wilson"]'
      )
      expect(remainingTooltip).toBeInTheDocument()
    })

    it('should not show remaining badge when all fit', () => {
      render(<AnnotatorBadges assignments={mockAssignments} maxVisible={5} />)

      expect(screen.queryByText(/^\+\d+$/)).not.toBeInTheDocument()
    })
  })

  describe('Color Generation', () => {
    it('should generate consistent colors for same user id', () => {
      const { container: container1 } = render(
        <AnnotatorBadges
          assignments={[
            {
              id: 'a1',
              user_id: 'consistent-id',
              user_name: 'Test User',
              user_email: 'test@example.com',
            },
          ]}
        />
      )

      const { container: container2 } = render(
        <AnnotatorBadges
          assignments={[
            {
              id: 'a2',
              user_id: 'consistent-id',
              user_name: 'Different Name',
              user_email: 'different@example.com',
            },
          ]}
        />
      )

      const badge1 = container1.querySelector('.rounded-full')
      const badge2 = container2.querySelector('.rounded-full')

      expect(badge1?.className).toBe(badge2?.className)
    })

    it('should generate different colors for different user ids', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'user-1',
          user_name: 'User 1',
          user_email: 'user1@example.com',
        },
        {
          id: 'a2',
          user_id: 'user-2',
          user_name: 'User 2',
          user_email: 'user2@example.com',
        },
      ]

      const { container } = render(
        <AnnotatorBadges assignments={assignments} />
      )

      const badges = container.querySelectorAll('.rounded-full')
      const classes1 = badges[0]?.className
      const classes2 = badges[1]?.className

      expect(classes1).not.toBe(classes2)
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty assignments array', () => {
      render(<AnnotatorBadges assignments={[]} />)

      expect(screen.getByText('Unassigned')).toBeInTheDocument()
    })

    it('should handle null assignments', () => {
      render(<AnnotatorBadges assignments={null as any} />)

      expect(screen.getByText('Unassigned')).toBeInTheDocument()
    })

    it('should handle undefined assignments', () => {
      render(<AnnotatorBadges assignments={undefined as any} />)

      expect(screen.getByText('Unassigned')).toBeInTheDocument()
    })

    it('should handle assignment without id', () => {
      const assignments = [
        {
          id: undefined as any,
          user_id: 'u1',
          user_name: 'John Doe',
          user_email: 'john@example.com',
        },
      ]

      render(<AnnotatorBadges assignments={assignments} />)

      expect(screen.getByText('JD')).toBeInTheDocument()
    })

    it('should handle very long names', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'Verylongnamethatshouldbetrimmed',
          user_email: 'long@example.com',
        },
      ]

      render(<AnnotatorBadges assignments={assignments} />)

      expect(screen.getByText('VE')).toBeInTheDocument()
    })

    it('should handle names with special characters', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'José María',
          user_email: 'jose@example.com',
        },
      ]

      render(<AnnotatorBadges assignments={assignments} />)

      expect(screen.getByText('JM')).toBeInTheDocument()
    })

    it('should handle single-character names', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: 'A',
          user_email: 'a@example.com',
        },
      ]

      render(<AnnotatorBadges assignments={assignments} />)

      expect(screen.getByText('A')).toBeInTheDocument()
    })

    it('should handle whitespace in names', () => {
      const assignments = [
        {
          id: 'a1',
          user_id: 'u1',
          user_name: '  John   Doe  ',
          user_email: 'john@example.com',
        },
      ]

      render(<AnnotatorBadges assignments={assignments} />)

      expect(screen.getByText('JD')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('should have proper button attributes for assign action', () => {
      const mockOnAssign = jest.fn()

      render(
        <AnnotatorBadges
          assignments={[]}
          canAssign={true}
          onAssign={mockOnAssign}
        />
      )

      const button = screen.getByText('+ Assign')
      expect(button.tagName).toBe('BUTTON')
    })

    it('should have title attribute on remove buttons', () => {
      const mockOnUnassign = jest.fn()
      const { container } = render(
        <AnnotatorBadges
          assignments={mockAssignments}
          canUnassign={true}
          onUnassign={mockOnUnassign}
        />
      )

      const removeButton = container.querySelector(
        '[title="Remove assignment"]'
      )
      expect(removeButton).toHaveAttribute('title', 'Remove assignment')
    })
  })
})
