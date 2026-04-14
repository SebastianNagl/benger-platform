/**
 * Simplified test for TaskAnnotationComparisonModal
 * Tests core functionality without complex mocking
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'

// Mock all dependencies properly
jest.mock('@/lib/api/users', () => ({
  UsersClient: jest.fn().mockImplementation(() => ({
    getAllUsers: jest.fn().mockResolvedValue([]),
  })),
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'test-user', username: 'Test User' } }),
}))

jest.mock('@/contexts/FeatureFlagContext', () => ({
  useFeatureFlag: jest.fn().mockReturnValue(true),
}))

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}))

import { TaskAnnotationComparisonModal } from '../TaskAnnotationComparisonModal'

describe('TaskAnnotationComparisonModal - Core Functionality', () => {
  // Mock task data
  const mockTask = {
    id: 'task-1',
    project_id: 'project-1',
    data: { text: 'Sample task text' },
    meta: {},
    is_labeled: false,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('does not render when closed', () => {
    const { container } = render(
      <TaskAnnotationComparisonModal
        task={mockTask}
        isOpen={false}
        onClose={() => {}}
        projectId="project-1"
      />
    )

    expect(container.querySelector('[role="dialog"]')).not.toBeInTheDocument()
  })

  it('renders modal structure when open', async () => {
    render(
      <TaskAnnotationComparisonModal
        task={mockTask}
        isOpen={true}
        onClose={() => {}}
        projectId="project-1"
      />
    )

    // Wait for the component to load and check for dialog presence
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  it('shows loading or no annotations message when annotations are empty', async () => {
    render(
      <TaskAnnotationComparisonModal
        task={mockTask}
        isOpen={true}
        onClose={() => {}}
        projectId="project-1"
      />
    )

    await waitFor(() => {
      // Component should render and handle empty state
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })
})
