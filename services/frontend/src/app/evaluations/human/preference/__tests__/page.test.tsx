/**
 * Tests for Preference Ranking Human Evaluation Interface
 * Issue #483: Comprehensive evaluation configuration system
 *
 * @jest-environment jsdom
 */

import { useToast } from '@/components/shared/Toast'
import { apiClient } from '@/lib/api/client'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useRouter, useSearchParams } from 'next/navigation'
import PreferenceEvaluation from '../page'

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
  EqualsIcon: () => <div data-testid="equals-icon" />,
  EyeSlashIcon: () => <div data-testid="eye-slash-icon" />,
  TrophyIcon: () => <div data-testid="trophy-icon" />,
  XMarkIcon: () => <div data-testid="x-mark-icon" />,
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
  }: {
    children: React.ReactNode
    onClick?: () => void
    disabled?: boolean
    variant?: string
  }) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant}>
      {children}
    </button>
  ),
}))

// Mock Card component
jest.mock('@/components/shared/Card', () => ({
  Card: ({
    children,
    onClick,
    className,
  }: {
    children: React.ReactNode
    onClick?: () => void
    className?: string
  }) => (
    <div onClick={onClick} className={className} data-testid="card">
      {children}
    </div>
  ),
}))

// Mock Badge component
jest.mock('@/components/shared/Badge', () => ({
  Badge: ({
    children,
    variant,
    className,
  }: {
    children: React.ReactNode
    variant?: string
    className?: string
  }) => (
    <span data-testid="badge" data-variant={variant} className={className}>
      {children}
    </span>
  ),
}))

describe('PreferenceEvaluation', () => {
  const mockRouter = {
    push: jest.fn(),
    replace: jest.fn(),
  }

  const mockSearchParams = {
    get: jest.fn(),
  }

  const mockAddToast = jest.fn()

  const mockSession = {
    id: 'session-123',
    project_id: 'project-456',
    project_name: 'Legal Document Analysis',
    total_items: 10,
    evaluated_items: 3,
    allow_ties: true,
  }

  const mockItem = {
    id: 'item-1',
    task_data: {
      question: 'What is the legal precedent?',
      context: 'Sample legal context',
    },
    responses: [
      {
        id: 'response-a',
        content: 'Response A content with detailed legal analysis',
        anonymized_id: 'Response A',
      },
      {
        id: 'response-b',
        content: 'Response B content with alternative perspective',
        anonymized_id: 'Response B',
      },
    ],
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

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/evaluations/human/session/start',
          {
            project_id: 'project-456',
            session_type: 'preference',
            config: {
              allow_ties: true,
              anonymize_sources: true,
            },
          }
        )
      })

      await waitFor(() => {
        expect(mockRouter.replace).toHaveBeenCalledWith(
          '/evaluations/human/preference?session=session-123'
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

      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    })

    it('hides loading spinner after data loads', async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<PreferenceEvaluation />)

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
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Human Preference Evaluation')).toBeInTheDocument()
        expect(
          screen.getByText(/Compare and rate model responses/)
        ).toBeInTheDocument()
      })
    })

    it('renders project name and progress', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Legal Document Analysis')).toBeInTheDocument()
        expect(screen.getByText(/Progress.*4.*10/)).toBeInTheDocument()
      })
    })

    it('renders progress bar with correct width', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        const progressText = screen.getByText(/Progress.*4.*10/)
        expect(progressText).toBeInTheDocument()
        const progressBar =
          progressText.parentElement?.nextElementSibling?.querySelector(
            '.bg-blue-600'
          )
        expect(progressBar).toBeInTheDocument()
      })
    })

    it('renders task data', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Task')).toBeInTheDocument()
        const taskDataElement = screen.getByText(/question/)
        expect(taskDataElement).toBeInTheDocument()
      })
    })

    it('renders both responses with anonymized IDs', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
        expect(screen.getByText('Response B')).toBeInTheDocument()
        expect(
          screen.getByText(/Response A content with detailed legal analysis/)
        ).toBeInTheDocument()
        expect(
          screen.getByText(/Response B content with alternative perspective/)
        ).toBeInTheDocument()
      })
    })

    it('renders evaluation guidelines', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Evaluation Guidelines')).toBeInTheDocument()
        expect(
          screen.getByText(/Responses are anonymized to prevent bias/)
        ).toBeInTheDocument()
      })
    })

    it('renders exit button', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Exit')).toBeInTheDocument()
      })
    })
  })

  describe('selection handling', () => {
    beforeEach(async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
    })

    it('allows selecting a winner by clicking response card', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1]) // Click first response card

      await waitFor(() => {
        expect(screen.getByText(/Prefer:/)).toBeInTheDocument()
      })
    })

    it('changes selection when different response is clicked', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')

      // Click first response
      await user.click(cards[1])
      await waitFor(() => {
        expect(screen.getByText(/Prefer:/)).toBeInTheDocument()
      })

      // Click second response
      await user.click(cards[2])
      await waitFor(() => {
        const winnerText = screen.getByText(/Prefer:/).parentElement
        expect(winnerText).toHaveTextContent('Response B')
      })
    })

    it('shows "Mark as Tie" button when ties are allowed', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Equal quality')).toBeInTheDocument()
      })
    })

    it('marks evaluation as tie when tie button is clicked', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Equal quality')).toBeInTheDocument()
      })

      const tieButton = screen.getByText('Equal quality')
      await user.click(tieButton)

      await waitFor(() => {
        expect(
          screen.getByText(/equally good, mark them as a tie/)
        ).toBeInTheDocument()
      })
    })

    it('clears winner selection when marking as tie', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

      await waitFor(() => {
        expect(screen.getByText(/Prefer:/)).toBeInTheDocument()
      })

      const tieButton = screen.getByText('Equal quality')
      await user.click(tieButton)

      await waitFor(() => {
        expect(screen.queryByText(/Prefer:/)).not.toBeInTheDocument()
        expect(
          screen.getByText(/equally good, mark them as a tie/)
        ).toBeInTheDocument()
      })
    })

    it('keeps tie selection when clicking a response card', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Equal quality')).toBeInTheDocument()
      })

      const tieButton = screen.getByText('Equal quality')
      await user.click(tieButton)

      await waitFor(() => {
        expect(
          screen.getByText(/equally good, mark them as a tie/)
        ).toBeInTheDocument()
      })

      // Click response card - should NOT clear tie (component guards with !isTie)
      const responseCards = screen.getAllByTestId('card')
      const firstResponseCard = responseCards.find((card) =>
        card.textContent?.includes('Response A content')
      )
      if (firstResponseCard) {
        await user.click(firstResponseCard)
      }

      // Tie selection should still be active
      await waitFor(() => {
        expect(
          screen.getByText(/equally good, mark them as a tie/)
        ).toBeInTheDocument()
      })
    })

    it('shows instruction when no selection is made', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(
          screen.getByText(/Select which response you prefer/)
        ).toBeInTheDocument()
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

    it('disables submit button when no selection is made', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        const submitButton = screen.getByText('Submit Evaluation')
        expect(submitButton).toBeDisabled()
      })
    })

    it('enables submit button when winner is selected', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

      await waitFor(() => {
        const submitButton = screen.getByText('Submit Evaluation')
        expect(submitButton).not.toBeDisabled()
      })
    })

    it('enables submit button when tie is marked', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Equal quality')).toBeInTheDocument()
      })

      const tieButton = screen.getByText('Equal quality')
      await user.click(tieButton)

      await waitFor(() => {
        const submitButton = screen.getByText('Submit Evaluation')
        expect(submitButton).not.toBeDisabled()
      })
    })

    it('submits preference with correct data when winner is selected', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/evaluations/human/session/session-123/submit',
          expect.objectContaining({
            item_id: 'item-1',
            evaluation_type: 'preference',
            preference_data: expect.objectContaining({
              winner: 'response-a',
              is_tie: false,
              ranking: ['response-a', 'response-b'],
              response_ids: ['response-a', 'response-b'],
            }),
          })
        )
      })
    })

    it('submits preference with correct data when tie is marked', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Equal quality')).toBeInTheDocument()
      })

      const tieButton = screen.getByText('Equal quality')
      await user.click(tieButton)

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/evaluations/human/session/session-123/submit',
          expect.objectContaining({
            item_id: 'item-1',
            evaluation_type: 'preference',
            preference_data: expect.objectContaining({
              winner: null,
              is_tie: true,
              ranking: ['response-a', 'response-b'],
              response_ids: ['response-a', 'response-b'],
            }),
          })
        )
      })
    })

    it('shows loading state while submitting', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

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

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

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
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText(/Progress.*4.*10/)).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(screen.getByText(/Progress.*5.*10/)).toBeInTheDocument()
      })
    })

    it('shows error toast when submission fails', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockRejectedValue(
        new Error('Network error')
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to submit evaluation',
          'error'
        )
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
      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

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

      render(<PreferenceEvaluation />)

      await waitFor(
        () => {
          expect(screen.getByText('Evaluation Complete')).toBeInTheDocument()
          expect(
            screen.getByText(/Thank you for evaluating all items/)
          ).toBeInTheDocument()
        },
        { timeout: 3000 }
      )
    })

    it('shows project name and evaluated count on completion', async () => {
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { completed: true } })

      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

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

  describe('reveal identities functionality', () => {
    beforeEach(async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
    })

    it('renders reveal model names button', async () => {
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Reveal Model Names')).toBeInTheDocument()
      })
    })

    it('shows model identities when reveal button is clicked', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Reveal Model Names')).toBeInTheDocument()
      })

      const revealButton = screen.getByText('Reveal Model Names')
      await user.click(revealButton)

      await waitFor(() => {
        expect(screen.getByText('Model Identities')).toBeInTheDocument()
        expect(screen.getByText(/Response A:/)).toBeInTheDocument()
        expect(screen.getByText(/Response B:/)).toBeInTheDocument()
      })
    })

    it('toggles reveal button text', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Reveal Model Names')).toBeInTheDocument()
      })

      const revealButton = screen.getByText('Reveal Model Names')
      await user.click(revealButton)

      await waitFor(() => {
        expect(screen.getByText('Hide Model Names')).toBeInTheDocument()
      })

      const hideButton = screen.getByText('Hide Model Names')
      await user.click(hideButton)

      await waitFor(() => {
        expect(screen.getByText('Reveal Model Names')).toBeInTheDocument()
      })
    })

    it('includes revealed identities in submission metadata', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Reveal Model Names')).toBeInTheDocument()
      })

      const revealButton = screen.getByText('Reveal Model Names')
      await user.click(revealButton)

      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      await waitFor(() => {
        expect(apiClient.post).toHaveBeenCalledWith(
          '/evaluations/human/session/session-123/submit',
          expect.objectContaining({
            metadata: expect.objectContaining({
              revealed_identities: true,
            }),
          })
        )
      })
    })
  })

  describe('exit functionality', () => {
    beforeEach(async () => {
      mockSearchParams.get.mockImplementation((key: string) =>
        key === 'session' ? 'session-123' : null
      )
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
    })

    it('redirects to evaluations page on exit', async () => {
      const user = userEvent.setup()
      render(<PreferenceEvaluation />)

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

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(mockAddToast).toHaveBeenCalledWith(
          'Failed to load next evaluation item',
          'error'
        )
      })
    })

    it('resets selection state when loading new item', async () => {
      const user = userEvent.setup()
      ;(apiClient.post as jest.Mock).mockResolvedValue({
        data: { success: true },
      })
      ;(apiClient.get as jest.Mock)
        .mockResolvedValueOnce({ data: mockSession })
        .mockResolvedValueOnce({ data: { item: mockItem } })
        .mockResolvedValueOnce({ data: { item: mockItem } })

      render(<PreferenceEvaluation />)

      await waitFor(() => {
        expect(screen.getByText('Response A')).toBeInTheDocument()
      })

      // Select winner
      const cards = screen.getAllByTestId('card')
      await user.click(cards[1])

      await waitFor(() => {
        expect(screen.getByText(/Prefer:/)).toBeInTheDocument()
      })

      // Submit
      const submitButton = screen.getByText('Submit Evaluation')
      await user.click(submitButton)

      // Wait for next item to load
      await waitFor(() => {
        expect(
          screen.getByText(/Select which response you prefer/)
        ).toBeInTheDocument()
      })
    })
  })
})
