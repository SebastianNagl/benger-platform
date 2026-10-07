/**
 * @jest-environment jsdom
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom'
import {
  fireEvent,
  render as rtlRender,
  screen,
  waitFor,
} from '@testing-library/react'
import React from 'react'

const render: typeof rtlRender = (ui, options) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return rtlRender(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
    options,
  )
}

const mockGetScores = jest.fn()
let mockUser: { id: string } | null = { id: 'u1' }

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    apiClient: {
      leaderboards: { getLLMModelProjectScores: mockGetScores },
    },
  }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) => {
      if (vars && typeof vars === 'object') {
        let out = key
        for (const [k, v] of Object.entries(vars)) {
          out = out.replace(`{${k}}`, String(v))
        }
        return out
      }
      return key
    },
    locale: 'en',
  }),
}))
// The shared Select is a Radix popover; in jsdom we swap it for a native
// <select> so the period change can be driven with fireEvent.
jest.mock('@/components/shared/Select', () => {
  const React = jest.requireActual('react')
  const Ctx = React.createContext<{
    value: string
    onValueChange: (v: string) => void
  } | null>(null)
  return {
    Select: ({ value, onValueChange, children }: any) => (
      <Ctx.Provider value={{ value, onValueChange }}>{children}</Ctx.Provider>
    ),
    SelectTrigger: ({ children, ...props }: any) => (
      <div {...props}>{children}</div>
    ),
    SelectValue: () => null,
    SelectContent: ({ children }: any) => {
      const ctx = React.useContext(Ctx)!
      return (
        <select
          data-testid="period-select"
          value={ctx.value}
          onChange={(e: any) => ctx.onValueChange(e.target.value)}
        >
          {children}
        </select>
      )
    },
    SelectItem: ({ value, children }: any) => (
      <option value={value}>{children}</option>
    ),
  }
})

import { formatValueForScale, getMetricScale } from '@/lib/api/evaluation-types'
import { ModelDetailModal } from '../ModelDetailModal'

const fmt = (key: string, v: number) =>
  formatValueForScale(v, getMetricScale(key), false)

const model = { id: 'gpt-4o', name: 'GPT-4o', provider: 'OpenAI' }

const response = {
  model_info: model,
  projects: [
    {
      project_id: 'p1',
      project_name: 'Alpha exam',
      project_kind: 'exam',
      is_public: true,
      evaluation_count: 2,
      generation_count: 40,
      samples_evaluated: 80,
      last_evaluated: '2026-10-01T10:00:00Z',
      metrics: {
        accuracy: { mean: 0.85, ci_lower: 0.8, ci_upper: 0.9, n: 80 },
        llm_judge_falloesung_grade_points: {
          mean: 9,
          ci_lower: null,
          ci_upper: null,
          n: 1,
        },
      },
    },
    {
      project_id: 'p2',
      project_name: 'Beta',
      project_kind: null,
      is_public: false,
      evaluation_count: 1,
      generation_count: 10,
      samples_evaluated: 10,
      last_evaluated: null,
      metrics: {
        accuracy: { mean: 0.5, ci_lower: null, ci_upper: null, n: 1 },
      },
    },
  ],
  available_metrics: ['accuracy', 'llm_judge_falloesung_grade_points'],
  filters: { period: 'overall' },
  computed_at: '2026-10-07T00:00:00Z',
}

describe('ModelDetailModal', () => {
  beforeEach(() => {
    mockGetScores.mockReset()
    mockUser = { id: 'u1' }
  })

  it('renders nothing while closed', () => {
    render(<ModelDetailModal model={null} onClose={jest.fn()} />)
    expect(mockGetScores).not.toHaveBeenCalled()
    expect(screen.queryByTestId('model-detail-modal')).not.toBeInTheDocument()
  })

  it('loads scores for the model and renders a row per project', async () => {
    mockGetScores.mockResolvedValue(response)
    render(<ModelDetailModal model={model} onClose={jest.fn()} />)

    await waitFor(() =>
      expect(mockGetScores).toHaveBeenCalledWith('gpt-4o', {
        period: 'overall',
      }),
    )
    await waitFor(() =>
      expect(screen.getByTestId('model-detail-table')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('model-detail-row-p1')).toBeInTheDocument()
    expect(screen.getByTestId('model-detail-row-p2')).toBeInTheDocument()
    expect(screen.getByText('Alpha exam').closest('a')).toHaveAttribute(
      'href',
      '/projects/p1',
    )
    expect(screen.getByText('models.detail.projectCount')).toBeInTheDocument()
  })

  it('formats metric cells by their registry scale and shows n and CI', async () => {
    mockGetScores.mockResolvedValue(response)
    render(<ModelDetailModal model={model} onClose={jest.fn()} />)
    await screen.findByTestId('model-detail-table')

    // accuracy is a 0-1 metric -> percent
    expect(screen.getByText('85.0%')).toBeInTheDocument()
    expect(screen.getByText('50.0%')).toBeInTheDocument()
    // grade points follow whatever scale the registry declares for the key
    expect(
      screen.getByText(fmt('llm_judge_falloesung_grade_points', 9)),
    ).toBeInTheDocument()
    // sample size + CI subtext on the first cell
    // the i18n mock returns the key; every scored cell carries the n label
    expect(screen.getAllByText('models.detail.samplesShort')).toHaveLength(3)
    expect(screen.getByText('[80.0% – 90.0%]')).toBeInTheDocument()
    // Beta has no grade points -> n/a
    expect(screen.getByText('models.detail.notAvailable')).toBeInTheDocument()
    // kind + public badges on Alpha
    expect(screen.getByText('projects.list.kindExam')).toBeInTheDocument()
    expect(screen.getByText('models.detail.publicProject')).toBeInTheDocument()
  })

  it('shows the empty state when no project has data', async () => {
    mockGetScores.mockResolvedValue({
      ...response,
      projects: [],
      available_metrics: [],
    })
    render(<ModelDetailModal model={model} onClose={jest.fn()} />)
    expect(await screen.findByTestId('model-detail-empty')).toBeInTheDocument()
    expect(screen.getByText('models.detail.noScoresTitle')).toBeInTheDocument()
  })

  it('shows an error with retry when the request fails', async () => {
    mockGetScores.mockRejectedValueOnce(new Error('boom'))
    mockGetScores.mockResolvedValueOnce(response)
    render(<ModelDetailModal model={model} onClose={jest.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'models.detail.loadError',
    )
    fireEvent.click(screen.getByText('models.detail.retry'))
    expect(await screen.findByTestId('model-detail-table')).toBeInTheDocument()
  })

  it('tells anonymous visitors that only public projects are shown', async () => {
    mockUser = null
    mockGetScores.mockResolvedValue(response)
    render(<ModelDetailModal model={model} onClose={jest.fn()} />)
    expect(
      await screen.findByText('models.detail.anonymousHint'),
    ).toBeInTheDocument()
  })

  it('refetches when the period changes', async () => {
    mockGetScores.mockResolvedValue(response)
    render(<ModelDetailModal model={model} onClose={jest.fn()} />)
    await screen.findByTestId('model-detail-table')

    fireEvent.change(screen.getByTestId('period-select'), {
      target: { value: 'weekly' },
    })
    await waitFor(() =>
      expect(mockGetScores).toHaveBeenCalledWith('gpt-4o', {
        period: 'weekly',
      }),
    )
  })

  it('keeps the technical JSON in a collapsed section with Copy JSON', async () => {
    mockGetScores.mockResolvedValue(response)
    const writeText = jest.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    const settings = { model: { id: 'gpt-4o' }, provider_settings: null }
    render(
      <ModelDetailModal
        model={model}
        settingsJson={settings}
        onClose={jest.fn()}
      />,
    )
    await screen.findByTestId('model-detail-table')

    expect(
      screen.getByText('models.detail.technicalDetails'),
    ).toBeInTheDocument()
    expect(screen.getByText(/provider_settings/)).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('model-detail-copy-json'))
    expect(writeText).toHaveBeenCalledWith(JSON.stringify(settings, null, 2))
  })

  it('hides the technical section without settings and closes via the button', async () => {
    mockGetScores.mockResolvedValue(response)
    const onClose = jest.fn()
    render(<ModelDetailModal model={model} onClose={onClose} />)
    await screen.findByTestId('model-detail-table')

    expect(
      screen.queryByText('models.detail.technicalDetails'),
    ).not.toBeInTheDocument()
    expect(screen.queryByTestId('model-detail-copy-json')).toBeNull()
    fireEvent.click(screen.getByText('models.close'))
    expect(onClose).toHaveBeenCalled()
  })
})
