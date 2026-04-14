/**
 * Tests for Likert Scale Human Evaluation Interface
 * Issue #483: Comprehensive evaluation configuration system
 *
 * @jest-environment jsdom
 */

import { useToast } from '@/components/shared/Toast'
import { apiClient } from '@/lib/api/client'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter, useSearchParams } from 'next/navigation'
import LikertEvaluation from '../page'

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}))

// Mock API client
jest.mock('@/lib/api/client', () => ({
  apiClient: {
    get: jest.fn(),
    post: jest.fn(),
  },
}))

// Mock Toast
jest.mock('@/components/shared/Toast', () => ({
  useToast: jest.fn(),
}))

// Mock FeatureFlag to render children
jest.mock('@/components/shared/FeatureFlag', () => ({
  FeatureFlag: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Mock AuthContext
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'test@example.com' },
    isAuthenticated: true,
    login: jest.fn(),
    logout: jest.fn(),
  }),
  AuthProvider: ({ children }: any) => <>{children}</>,
}))

// Mock I18n
// Create stable mock function outside the mock factory
const mockT = (key: string) => key

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, varsOrDefault?: any) => {
      const translations: Record<string, any> = require('../../../../../locales/en/common.json')
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

// Mock Heroicons
jest.mock('@heroicons/react/24/outline', () => ({
  ArrowRightIcon: () => <div data-testid="arrow-right-icon" />,
  CheckCircleIcon: () => <div data-testid="check-circle-icon" />,
  StarIcon: () => <div data-testid="star-icon-outline" />,
  XMarkIcon: () => <div data-testid="x-mark-icon" />,
}))

jest.mock('@heroicons/react/24/solid', () => ({
  StarIcon: () => <div data-testid="star-icon-solid" />,
}))

// Mock LoadingSpinner
jest.mock('@/components/shared/LoadingSpinner', () => ({
  LoadingSpinner: ({ className }: { className?: string }) => (
    <div data-testid="loading-spinner" className={className}>
      Loading...
    </div>
  ),
}))

// Mock Button component
jest.mock('@/components/shared/Button', () => ({
  Button: ({
    children,
    onClick,
    disabled,
    variant,
    className,
  }: {
    children: React.ReactNode
    onClick?: () => void
    disabled?: boolean
    variant?: string
    className?: string
  }) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-variant={variant}
      className={className}
    >
      {children}
    </button>
  ),
}))

// Mock Card component
jest.mock('@/components/shared/Card', () => ({
  Card: ({
    children,
    className,
  }: {
    children: React.ReactNode
    className?: string
  }) => (
    <div className={className} data-testid="card">
      {children}
    </div>
  ),
}))

// Mock Badge component
jest.mock('@/components/shared/Badge', () => ({
  Badge: ({
    children,
    variant,
  }: {
    children: React.ReactNode
    variant?: string
  }) => (
    <span data-testid="badge" data-variant={variant}>
      {children}
    </span>
  ),
}))

describe('LikertEvaluation', () => {
  const mockRouter = {
    push: jest.fn(),
    replace: jest.fn(),
  }

  const mockSearchParams = {
    get: jest.fn(),
  }

  const mockAddToast = jest.fn()

  const mockDimensions = [
    {
      id: 'accuracy',
      name: 'Accuracy',
      description: 'Criterion',
    },
    {
      id: 'clarity',
      name: 'Clarity',
      description: 'Criterion',
    },
    {
      id: 'relevance',
      name: 'Relevance',
      description: 'Criterion',
    },
    {
      id: 'completeness',
      name: 'Completeness',
      description: 'Criterion',
    },
  ]

  const mockSession = {
    id: 'session-123',
    project_id: 'project-456',
    project_name: 'Legal Document Analysis',
    total_items: 10,
    evaluated_items: 3,
    dimensions: mockDimensions,
  }

  const mockItem = {
    id: 'item-1',
    task_data: {
      question: 'What is the legal precedent?',
      context: 'Sample legal context',
    },
    response_content:
      'This is a detailed legal response with comprehensive analysis.',
    model_id: 'gpt-4',
  }

  beforeEach(() => {
    jest.clearAllMocks()
    // Reset API client mocks to clear any queued mockResolvedValueOnce
    ;(apiClient.get as jest.Mock).mockReset()
    ;(apiClient.post as jest.Mock).mockReset()
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useSearchParams as jest.Mock).mockReturnValue(mockSearchParams)
    ;(useToast as jest.Mock).mockReturnValue({ addToast: mockAddToast })
  })

  describe('initialization', () => {
    it('creates new session when project ID is provided', async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'project' ? 'project-456' : null
      )
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: mockSession,
      })
      ;(apiClient.get as jest.Mock).mockResolvedValue({
        data: { item: mockItem },
      })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/evaluations/human/session/start',
          {
            project_id: 'project-456',
            session_type: 'likert',
            dimensions: [
              {
                id: 'accuracy',
                name: 'Accuracy',
                description: 'Criterion',
              },
              {
                id: 'clarity',
                name: 'Clarity',
                description: 'Criterion',
              },
              {
                id: 'relevance',
                name: 'Relevance',
                description: 'Criterion',
              },
              {
                id: 'completeness',
                name: 'Completeness',
                description: 'Criterion',
              },
            ],
          }
        )
      })

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith(
          '/evaluations/human/likert?session=session-123'
        )
      })
    })

    it('loads existing session when session ID is provided', async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/evaluations/human/session/session-123'
        )
      })

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/evaluations/human/session/session-123/next'
        )
      })
    })

    it('redirects when no project or session is specified', async () => {
      mockSearchParams.get.mockReturnValue(null)

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'No project or session specified',
          'error'
        )
        expect(mockRouter.push).toHaveBeenCalledWith('/evaluations')
      })
    })

    it('handles session creation error', async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'project' ? 'project-456' : null
      )
      ;(apiClient.post as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to create evaluation session',
          'error'
        )
        expect(mockRouter.push).toHaveBeenCalledWith('/evaluations')
      })
    })

    it('handles session load error', async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock).mockRejectedValue(
        new Error('Session not found')
      )

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to load evaluation session',
          'error'
        )
        expect(mockRouter.push).toHaveBeenCalledWith('/evaluations')
      })
    })
  })

  describe('loading state', () => {
    it('shows loading spinner initially', () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      )

      render(<LikertEvaluation />)

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })

    it('hides loading spinner after data loads', async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument()
      })
    })
  })

  describe('page rendering', () => {
    beforeEach(async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
    })

    it('renders page title and header', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Likert Scale Evaluation')).toBeInTheDocument()
      })
    })

    it('renders project name and progress', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Legal Document Analysis')).toBeInTheDocument()
        expect(screen.getByText(/Progress.*4.*10/)).toBeInTheDocument()
      })
    })

    it('renders progress bar with correct width', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        const progressText = screen.getByText(/Progress.*4.*10/)
        expect(progressText).toBeInTheDocument()
        const progressBar =
          progressText.parentElement?.parentElement?.querySelector(
            '.bg-blue-600'
          )
        expect(progressBar).toBeInTheDocument()
      })
    })

    it('renders task data', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Task Data')).toBeInTheDocument()
        expect(
          screen.getByText(/What is the legal precedent?/)
        ).toBeInTheDocument()
      })
    })

    it('renders model response with model ID badge', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Model Response')).toBeInTheDocument()
        expect(screen.getByText('gpt-4')).toBeInTheDocument()
        expect(
          screen.getByText(/This is a detailed legal response/)
        ).toBeInTheDocument()
      })
    })

    it('renders all rating dimensions', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
        expect(screen.getByText('Clarity')).toBeInTheDocument()
        expect(screen.getByText('Relevance')).toBeInTheDocument()
        expect(screen.getByText('Completeness')).toBeInTheDocument()
      })
    })

    it('renders dimension descriptions', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        const descriptions = screen.getAllByText(
          'Criterion'
        )
        expect(descriptions.length).toBeGreaterThan(0)
      })
    })

    it('renders rating guidelines', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Rating Guidelines')).toBeInTheDocument()
        expect(
          screen.getByText(
            /Rate each dimension from 1 \(Poor\) to 5 \(Excellent\)/
          )
        ).toBeInTheDocument()
      })
    })

    it('renders exit button', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Exit')).toBeInTheDocument()
      })
    })
  })

  describe('star rating interaction', () => {
    beforeEach(async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
    })

    it('shows "Not rated" initially for all dimensions', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        const notRatedElements = screen.getAllByText('Not rated')
        expect(notRatedElements).toHaveLength(4)
      })
    })

    it('allows rating a dimension', async () => {
      const user = userEvent.setup()
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const allRate4Buttons = screen.getAllByLabelText('Rate 4 stars')
      await user.click(allRate4Buttons[0])

      await waitFor(() => {
        expect(screen.getByText('4/5')).toBeInTheDocument()
      })
    })

    it('allows rating all dimensions independently', async () => {
      const user = userEvent.setup()
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)

      // Rate accuracy as 5
      await user.click(allRateButtons[4])

      // Rate clarity as 3
      await user.click(allRateButtons[7])

      // Rate relevance as 4
      await user.click(allRateButtons[13])

      // Rate completeness as 2
      await user.click(allRateButtons[16])

      await waitFor(() => {
        expect(screen.getByText('5/5')).toBeInTheDocument()
        expect(screen.getByText('3/5')).toBeInTheDocument()
        expect(screen.getByText('4/5')).toBeInTheDocument()
        expect(screen.getByText('2/5')).toBeInTheDocument()
      })
    })

    it('allows changing a rating', async () => {
      const user = userEvent.setup()
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      // First rate as 3
      const allRate3Buttons = screen.getAllByLabelText('Rate 3 stars')
      await user.click(allRate3Buttons[0])

      await waitFor(() => {
        expect(screen.getByText('3/5')).toBeInTheDocument()
      })

      // Then change to 5
      const allRate5Buttons = screen.getAllByLabelText('Rate 5 stars')
      await user.click(allRate5Buttons[0])

      await waitFor(() => {
        expect(screen.getByText('5/5')).toBeInTheDocument()
      })
    })
  })

  describe('submit functionality', () => {
    beforeEach(async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
    })

    it('disables submit button when no ratings are provided', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        const submitButton = screen.getByText('Submit Evaluation')
        expect(submitButton).toBeDisabled()
      })
    })

    it('shows error toast when submitting with missing ratings', async () => {
      const user = userEvent.setup()
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      // Rate only accuracy (first dimension)
      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)
      await user.click(allRateButtons[4]) // Accuracy: 5

      await waitFor(() => {
        const submitButton = screen.getByText('Submit Evaluation')
        expect(submitButton).not.toBeDisabled()
      })

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Please rate all dimensions: Clarity, Relevance, Completeness',
          'error'
        )
      })
    })

    it('enables submit button when all dimensions are rated', async () => {
      const user = userEvent.setup()
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)

      // Rate all 4 dimensions
      await user.click(allRateButtons[4]) // Accuracy: 5
      await user.click(allRateButtons[7]) // Clarity: 3
      await user.click(allRateButtons[13]) // Relevance: 4
      await user.click(allRateButtons[16]) // Completeness: 2

      await waitFor(() => {
        const submitButton = screen.getByText('Submit Evaluation')
        expect(submitButton).not.toBeDisabled()
      })
    })

    it('submits ratings with correct data', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)

      await user.click(allRateButtons[4]) // Accuracy: 5
      await user.click(allRateButtons[7]) // Clarity: 3
      await user.click(allRateButtons[13]) // Relevance: 4
      await user.click(allRateButtons[16]) // Completeness: 2

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/evaluations/human/session/session-123/submit',
          expect.objectContaining({
            item_id: 'item-1',
            evaluation_type: 'likert',
            ratings: {
              accuracy: 5,
              clarity: 3,
              relevance: 4,
              completeness: 2,
            },
            metadata: expect.objectContaining({
              model_id: 'gpt-4',
              response_length: mockItem.response_content.length,
            }),
          })
        )
      })
    })

    it('shows loading state while submitting', async () => {
      const user = userEvent.setup()
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
      ;(apiClient.post as jest.Mock).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      )

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)
      await user.click(allRateButtons[4])
      await user.click(allRateButtons[7])
      await user.click(allRateButtons[13])
      await user.click(allRateButtons[16])

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(submitButton).toBeDisabled()
        expect(
          within(submitButton).getByTestId('loading-spinner')
        ).toBeInTheDocument()
      })
    })

    it('loads next item after successful submission', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)
      await user.click(allRateButtons[4])
      await user.click(allRateButtons[7])
      await user.click(allRateButtons[13])
      await user.click(allRateButtons[16])

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/evaluations/human/session/session-123/next'
        )
      })
    })

    it('updates progress after submission', async () => {
      const user = userEvent.setup()
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText(/Progress.*4.*10/)).toBeInTheDocument()
      })

      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)
      await user.click(allRateButtons[4])
      await user.click(allRateButtons[7])
      await user.click(allRateButtons[13])
      await user.click(allRateButtons[16])

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText(/Progress.*5.*10/)).toBeInTheDocument()
      })
    })

    it('shows error toast when submission fails', async () => {
      const user = userEvent.setup()
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.post as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)
      await user.click(allRateButtons[4])
      await user.click(allRateButtons[7])
      await user.click(allRateButtons[13])
      await user.click(allRateButtons[16])

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to submit evaluation',
          'error'
        )
      })
    })

    it('resets ratings when loading new item', async () => {
      const user = userEvent.setup()
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      // Rate all dimensions
      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)
      await user.click(allRateButtons[4])
      await user.click(allRateButtons[7])
      await user.click(allRateButtons[13])
      await user.click(allRateButtons[16])

      await waitFor(() => {
        expect(screen.getByText('5/5')).toBeInTheDocument()
      })

      // Submit
      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      // Wait for next item to load - ratings should be reset
      await waitFor(() => {
        const notRatedElements = screen.getAllByText('Not rated')
        expect(notRatedElements.length).toBeGreaterThan(0)
      })
    })
  })

  describe('skip functionality', () => {
    beforeEach(async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
    })

    it('renders skip button', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Skip')).toBeInTheDocument()
      })
    })

    it('skips current item and loads next', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Skip')).toBeInTheDocument()
      })

      const skipButton = screen.getByText('Skip')
      await user.click(skipButton)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/evaluations/human/session/session-123/skip',
          { item_id: 'item-1' }
        )
      })

      await waitFor(() => {
        expect(apiClient.get).toHaveBeenCalledWith(
          '/evaluations/human/session/session-123/next'
        )
      })
    })

    it('shows error when skip fails', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Skip')).toBeInTheDocument()
      })

      const skipButton = screen.getByText('Skip')
      await user.click(skipButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to skip item',
          'error'
        )
      })
    })

    it('disables skip button while submitting', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const allRateButtons = screen.getAllByLabelText(/Rate \d stars/)
      await user.click(allRateButtons[4])
      await user.click(allRateButtons[7])
      await user.click(allRateButtons[13])
      await user.click(allRateButtons[16])

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        const skipButton = screen.getByText('Skip')
        expect(skipButton).toBeDisabled()
      })
    })
  })

  describe('completion state', () => {
    beforeEach(() => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
    })

    it('shows completion screen when all items are evaluated', async () => {
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { completed: true } })

      render(<LikertEvaluation />)

      await waitFor(
        () => {
          expect(screen.getByText('Evaluation Complete')).toBeInTheDocument()
          expect(
            screen.getByText(
              /Rate model responses on multiple criteria/
            )
          ).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('shows project name and evaluated count on completion', async () => {
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { completed: true } })

      render(<LikertEvaluation />)

      await waitFor(
        () => {
          expect(
            screen.getByText('Legal Document Analysis')
          ).toBeInTheDocument()
          expect(screen.getByText('3')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('renders return to dashboard button on completion', async () => {
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { completed: true } })

      render(<LikertEvaluation />)

      await waitFor(
        () => {
          expect(screen.getByText('Next Comparison')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('redirects to evaluations dashboard on button click', async () => {
      const user = userEvent.setup()
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { completed: true } })

      render(<LikertEvaluation />)

      await waitFor(
        () => {
          expect(screen.getByText('Next Comparison')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )

      const returnButton = screen.getByText('Next Comparison')
      await user.click(returnButton)

      expect(mockRouter.push).toHaveBeenCalledWith('/evaluations')
    })
  })

  describe('exit functionality', () => {
    it('redirects to evaluations page on exit', async () => {
      const user = userEvent.setup()
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Exit')).toBeInTheDocument()
      })

      const exitButton = screen.getByText('Exit')
      await user.click(exitButton)

      expect(mockRouter.push).toHaveBeenCalledWith('/evaluations')
    })
  })

  describe('error handling', () => {
    beforeEach(() => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
    })

    it('handles error when loading next item fails', async () => {
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockRejectedValueOnce(new Error('Failed to load next item'))

      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to load next evaluation item',
          'error'
        )
      })
    })

    it('sets showCompletion state when next item returns completed', async () => {
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { completed: true } })

      render(<LikertEvaluation />)

      await waitFor(
        () => {
          expect(screen.getByText('Evaluation Complete')).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })
  })

  describe('5-point scale', () => {
    beforeEach(async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
    })

    it('renders 5 star buttons for each dimension', async () => {
      render(<LikertEvaluation />)

      await waitFor(() => {
        const star1Buttons = screen.getAllByLabelText('Rate 1 stars')
        const star2Buttons = screen.getAllByLabelText('Rate 2 stars')
        const star3Buttons = screen.getAllByLabelText('Rate 3 stars')
        const star4Buttons = screen.getAllByLabelText('Rate 4 stars')
        const star5Buttons = screen.getAllByLabelText('Rate 5 stars')

        expect(star1Buttons).toHaveLength(4) // 4 dimensions
        expect(star2Buttons).toHaveLength(4)
        expect(star3Buttons).toHaveLength(4)
        expect(star4Buttons).toHaveLength(4)
        expect(star5Buttons).toHaveLength(4)
      })
    })

    it('displays rating as fraction of 5', async () => {
      const user = userEvent.setup()
      render(<LikertEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Accuracy')).toBeInTheDocument()
      })

      const allRate3Buttons = screen.getAllByLabelText('Rate 3 stars')
      await user.click(allRate3Buttons[0]) // Click first dimension's 3-star button

      await waitFor(() => {
        expect(screen.getByText('3/5')).toBeInTheDocument()
      })
    })
  })
})
