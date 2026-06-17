/**
 * Tests for Generation Run Detail Page (multi-run feature).
 *
 * Behavioral coverage for the previously-untested
 * `app/generations/[id]/page.tsx`: load / error / not-found states, the
 * summary card, per-trial breakdown (multi-run vs single-run), linked
 * evaluations navigation, parameters / prompt blocks, and the
 * `StatusBadge` / `fmtDate` helpers exercised through the rendered DOM.
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock React.use() to synchronously unwrap the params promise.
jest.mock('react', () => {
  const actualReact = jest.requireActual('react')
  return {
    ...actualReact,
    use: jest.fn((value: any) => value),
  }
})

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

// Default-export apiClient (the module under test imports `apiClient from '@/lib/api'`).
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
  },
}))

jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <div data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </div>
  ),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, variant, className }: any) => (
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

jest.mock('@/components/shared/Badge', () => ({
  Badge: ({ children, variant }: any) => (
    <span data-testid="badge" data-variant={variant}>
      {children}
    </span>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div data-testid="card" className={className}>
      {children}
    </div>
  ),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowLeftIcon: () => <div data-testid="arrow-left-icon" />,
}))

import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import * as React from 'react'
import { useRouter } from 'next/navigation'
import GenerationRunDetailPage from '../page'

const mockRouter = {
  push: jest.fn(),
  back: jest.fn(),
  replace: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
}

// t() returns the provided fallback (second arg) when present, mirroring
// how the page calls t('key', 'German fallback').
const mockT = (key: string, fallback?: string) => fallback ?? key

const baseDetail = {
  id: 'gen-run-123',
  project_id: 'project-9',
  project_title: 'My Project',
  task_id: 'task-7',
  model_id: 'gpt-4o',
  structure_key: 'falloesung',
  status: 'completed',
  created_at: '2026-01-01T10:00:00Z',
  completed_at: '2026-01-01T10:05:00Z',
  runs_requested: 1,
  runs_completed: 1,
  runs_failed: 0,
  parameters: null,
  prompt_used: null,
  children: [],
  linked_evaluations: [],
}

describe('GenerationRunDetailPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    ;(React.use as jest.Mock).mockImplementation((value: any) => {
      if (value && typeof value.then === 'function') {
        return { id: 'gen-run-123' }
      }
      return value
    })
    ;(useRouter as jest.Mock).mockReturnValue(mockRouter)
    ;(useI18n as jest.Mock).mockReturnValue({ t: mockT })
    ;(apiClient.get as jest.Mock).mockResolvedValue(baseDetail)
  })

  it('shows loading state before data resolves', () => {
    ;(apiClient.get as jest.Mock).mockReturnValue(new Promise(() => {}))
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    expect(screen.getByText('Lade…')).toBeInTheDocument()
  })

  it('fetches the run on mount via /runs/generations/{id}', async () => {
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(apiClient.get).toHaveBeenCalledWith('/runs/generations/gen-run-123')
    })
  })

  it('renders the summary card with model, run counts and project title', async () => {
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('gpt-4o')).toBeInTheDocument()
    })
    // run counts "1/1"
    expect(screen.getByText('1/1')).toBeInTheDocument()
    // project title appears in subtitle and breadcrumb context
    expect(screen.getAllByText(/My Project/).length).toBeGreaterThan(0)
    // status badge
    expect(screen.getByTestId('badge')).toHaveTextContent('completed')
  })

  it('shows run-failed count suffix when runs_failed > 0', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ...baseDetail,
      runs_requested: 3,
      runs_completed: 2,
      runs_failed: 1,
    })
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText(/2\/3/)).toBeInTheDocument()
    })
    expect(screen.getByText(/1 fehlgeschlagen/)).toBeInTheDocument()
  })

  it('renders error state when fetch rejects with a message', async () => {
    ;(apiClient.get as jest.Mock).mockRejectedValue(new Error('boom'))
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('boom')).toBeInTheDocument()
    })
  })

  it('renders fallback error message when fetch rejects without a message', async () => {
    ;(apiClient.get as jest.Mock).mockRejectedValue({})
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('Failed to load generation run')).toBeInTheDocument()
    })
  })

  it('renders "Not found" when the API resolves to null', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue(null)
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('Not found')).toBeInTheDocument()
    })
  })

  it('navigates back to /runs?type=generation from the error state', async () => {
    const user = userEvent.setup()
    ;(apiClient.get as jest.Mock).mockResolvedValue(null)
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('Not found')).toBeInTheDocument()
    })
    await user.click(screen.getByText('Zurück'))
    expect(mockRouter.push).toHaveBeenCalledWith('/runs?type=generation')
  })

  it('renders the failed error banner with the error message', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ...baseDetail,
      status: 'failed',
      error_message: 'Provider rejected the request',
    })
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(
        screen.getByText('Provider rejected the request')
      ).toBeInTheDocument()
    })
  })

  it('renders the parameters block as pretty JSON', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ...baseDetail,
      parameters: { temperature: 0.7, max_tokens: 512 },
    })
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('Parameter')).toBeInTheDocument()
    })
    expect(screen.getByText(/"temperature": 0.7/)).toBeInTheDocument()
  })

  it('renders the per-trial breakdown table for multi-run with error and preview rows', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ...baseDetail,
      runs_requested: 2,
      runs_completed: 1,
      runs_failed: 1,
      children: [
        {
          id: 'child-1',
          run_index: 0,
          status: 'completed',
          completed_at: '2026-01-01T10:03:00Z',
          has_response: true,
          response_preview: 'Hello world preview',
          error_message: null,
        },
        {
          id: 'child-2',
          run_index: 1,
          status: 'failed',
          completed_at: null,
          has_response: false,
          response_preview: null,
          error_message: 'child failed',
        },
      ],
    })
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('Pro Lauf')).toBeInTheDocument()
    })
    expect(screen.getByText('Hello world preview')).toBeInTheDocument()
    expect(screen.getByText('child failed')).toBeInTheDocument()
    // Two run-index cells rendered
    expect(screen.getByText('0')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('renders the single-run response preview (no per-trial table)', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ...baseDetail,
      runs_requested: 1,
      children: [
        {
          id: 'child-1',
          run_index: 0,
          status: 'completed',
          completed_at: '2026-01-01T10:03:00Z',
          has_response: true,
          response_preview: 'Single run answer',
          error_message: null,
        },
      ],
    })
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('Antwort')).toBeInTheDocument()
    })
    expect(screen.getByText('Single run answer')).toBeInTheDocument()
    // The multi-run "Pro Lauf" heading must NOT appear
    expect(screen.queryByText('Pro Lauf')).not.toBeInTheDocument()
  })

  it('renders linked evaluations and navigates to the eval page on row click', async () => {
    const user = userEvent.setup()
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ...baseDetail,
      linked_evaluations: [
        {
          evaluation_id: 'eval-55',
          metric: 'llm_judge_falloesung',
          status: 'completed',
          completed_at: '2026-01-02T09:00:00Z',
          samples_evaluated: 12,
        },
      ],
    })
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('Verknüpfte Evaluierungen')).toBeInTheDocument()
    })
    await user.click(screen.getByText('llm_judge_falloesung'))
    expect(mockRouter.push).toHaveBeenCalledWith('/evaluations/eval-55')
  })

  it('navigates to the project from the project button in the summary card', async () => {
    const user = userEvent.setup()
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('gpt-4o')).toBeInTheDocument()
    })
    // The summary card renders a <button> whose label is the project title.
    const projectButton = screen
      .getAllByRole('button')
      .find((b) => b.textContent === 'My Project')
    expect(projectButton).toBeDefined()
    await user.click(projectButton!)
    expect(mockRouter.push).toHaveBeenCalledWith('/projects/project-9')
  })

  it('renders the prompt-used block when present', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      ...baseDetail,
      prompt_used: 'You are a helpful legal assistant.',
    })
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      expect(screen.getByText('Verwendeter Prompt')).toBeInTheDocument()
    })
    expect(
      screen.getByText('You are a helpful legal assistant.')
    ).toBeInTheDocument()
  })

  it('renders em-dash placeholders when optional fields are missing', async () => {
    ;(apiClient.get as jest.Mock).mockResolvedValue({
      id: 'gen-run-123',
      status: null,
      model_id: null,
      task_id: null,
      structure_key: null,
      created_at: null,
      completed_at: null,
      children: [],
    })
    render(<GenerationRunDetailPage params={Promise.resolve({ id: 'gen-run-123' })} />)
    await waitFor(() => {
      // StatusBadge with null status renders a dash; fmtDate(null) renders a dash.
      expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    })
  })
})
