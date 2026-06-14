/**
 * @jest-environment jsdom
 *
 * Behavioral interaction + branch coverage for LLMLeaderboardTable.
 *
 * Covers branches the existing LLMLeaderboardTable.test.tsx /
 * LLMLeaderboardTable.br5.test.tsx leave untouched:
 *   - medal icons for ranks 1/2/3 and the numeric default
 *   - score + confidence-interval formatting (percent scale, sum aggregation)
 *   - the "n/a" / muted-row path for entries without a score for the metric
 *   - the error state's Retry button (refetch)
 *   - the empty-leaderboard state
 *   - Pagination rendering + page change when total_models > page size
 *   - the "available metrics" footer including the "and more" overflow
 *   - period / metric / aggregation Select changes resetting to page 1
 *   - the FilterToolbar clear-all reset
 *   - the project-filter Menu toggle and the min-samples / include-all checkbox
 *
 * Mirrors the render + mock idiom of the two passing leaderboard test files:
 * a local QueryClient-wrapping render and inline jest.mock of the contexts.
 * The shared Select is globally mapped to a native-<select> mock
 * (see jest.config.js moduleNameMapper), so period/metric/aggregation are
 * real comboboxes we can drive with selectOptions / fireEvent.change.
 */
import '@testing-library/jest-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  fireEvent,
  render as rtlRender,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'

const render: typeof rtlRender = (ui, options) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return rtlRender(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
    options
  )
}

const mockGetLLMLeaderboard = jest.fn()

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', name: 'Test', is_superadmin: true },
    apiClient: {
      leaderboards: { getLLMLeaderboard: mockGetLLMLeaderboard },
    },
  }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) =>
      params ? `${key}:${JSON.stringify(params)}` : key,
    locale: 'en',
  }),
}))
jest.mock('@/hooks/useProjects', () => ({
  useProjects: () => ({
    projects: [
      { id: 'p1', title: 'Project Alpha' },
      { id: 'p2', title: 'Project Beta' },
    ],
    loading: false,
    fetchProjects: jest.fn(),
  }),
}))
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
  useSearchParams: () => ({ get: jest.fn() }),
}))

// HeadlessUI's Menu doesn't open / render its panel reliably under JSDOM
// (the project FilterDropdown tests mock it for the same reason). Replace
// it with a simple stateful version that toggles its items on button click
// and invokes the Menu.Item render-prop with `active: false`, so the
// project-filter menu items (and toggleProject) are exercised behaviorally.
jest.mock('@headlessui/react', () => {
  const React = require('react')
  const Ctx = React.createContext({ open: false, setOpen: (_: boolean) => {} })

  const Menu = ({ children, as: As = 'div', ...rest }: any) => {
    const [open, setOpen] = React.useState(false)
    return React.createElement(
      As === 'div' ? 'div' : As,
      rest,
      React.createElement(Ctx.Provider, { value: { open, setOpen } }, children)
    )
  }
  Menu.Button = ({ children, as: As, ...rest }: any) => {
    const { open, setOpen } = React.useContext(Ctx)
    const Comp = As || 'button'
    return React.createElement(
      Comp,
      { ...rest, onClick: () => setOpen(!open) },
      children
    )
  }
  Menu.Items = ({ children }: any) => {
    const { open } = React.useContext(Ctx)
    if (!open) return null
    return React.createElement('div', { role: 'menu' }, children)
  }
  Menu.Item = ({ children }: any) =>
    typeof children === 'function' ? children({ active: false }) : children

  return { Menu }
})

import { LLMLeaderboardTable } from '../LLMLeaderboardTable'

const baseFilters = {
  project_ids: [],
  period: 'overall',
  metric: 'average',
  aggregation: 'average',
  evaluation_types: [],
  include_all_models: false,
  limit: 50,
}

const emptyResponse = {
  leaderboard: [],
  total_models: 0,
  available_metrics: [],
  available_evaluation_types: [],
  filters: baseFilters,
  confidence_intervals_available: false,
}

// Three top entries (medals) plus a fourth with no score for the metric (n/a).
const dataResponse = {
  leaderboard: [
    {
      rank: 1,
      model_id: 'gpt-4o',
      model_name: 'GPT-4o',
      provider: 'OpenAI', // mixed case -> exercises provider.toLowerCase() lookup
      evaluation_count: 10,
      generation_count: 1234,
      samples_evaluated: 500,
      // The default selected metric is llm_judge_falloesung_grade_points, so
      // the displayed score reads from that key. accuracy is kept for the
      // "switch metric" test.
      metrics: { llm_judge_falloesung_grade_points: 0.9, accuracy: 0.92 },
      average_score: 0.9,
      ci_lower: 0.85,
      ci_upper: 0.95,
      last_evaluated: '2026-01-15T10:00:00Z',
    },
    {
      rank: 2,
      model_id: 'claude',
      model_name: 'Claude 3',
      provider: 'anthropic',
      evaluation_count: 8,
      generation_count: 800,
      samples_evaluated: 400,
      metrics: { llm_judge_falloesung_grade_points: 0.85, accuracy: 0.82 },
      average_score: 0.85,
      ci_lower: null, // ci missing -> formatCI returns null branch
      ci_upper: null,
      last_evaluated: null,
    },
    {
      rank: 3,
      model_id: 'gemini',
      model_name: 'Gemini',
      provider: 'google',
      evaluation_count: 6,
      generation_count: 600,
      samples_evaluated: 300,
      metrics: { llm_judge_falloesung_grade_points: 0.78, accuracy: 0.78 },
      average_score: 0.78,
      ci_lower: 0.7,
      ci_upper: 0.86,
      last_evaluated: null,
    },
    {
      rank: 7,
      model_id: 'mystery',
      model_name: 'MysteryModel',
      provider: 'weird_provider', // not in providerColors -> unknown fallback + default medal
      evaluation_count: 0,
      generation_count: 0,
      samples_evaluated: 0,
      metrics: {}, // no 'accuracy' -> getDisplayScore null -> n/a row
      average_score: null,
      ci_lower: null,
      ci_upper: null,
      last_evaluated: null,
    },
  ],
  total_models: 120, // > pageSize(50) -> Pagination shows multiple pages
  available_metrics: Array.from({ length: 13 }, (_, i) => `metric_${i}`), // > 10 -> "and more"
  available_evaluation_types: ['automated', 'human'],
  filters: baseFilters,
  confidence_intervals_available: true,
}

/**
 * Helper: find the metric <select> (the one whose options include the
 * accuracy core metric). The toolbar renders several comboboxes (period,
 * metric, aggregation, per-page) so we identify by option content.
 */
function findSelectByOption(optionText: string): HTMLSelectElement {
  const selects = screen.getAllByRole('combobox') as HTMLSelectElement[]
  const match = selects.find((sel) =>
    within(sel).queryAllByRole('option').some((o) => o.textContent === optionText)
  )
  if (!match) {
    throw new Error(`No <select> with an option "${optionText}" found`)
  }
  return match
}

/**
 * The period/metric/aggregation Selects and the include-all / min-samples
 * checkboxes live inside FilterToolbar.Field children, which the real
 * FilterToolbar only mounts after the "Filters" toggle is clicked
 * (showFilters defaults to false). Open the panel before driving them.
 */
async function openFilterPanel() {
  const filtersToggle = screen.getByTitle('common.filters.filters')
  await userEvent.click(filtersToggle)
}

describe('LLMLeaderboardTable interactions', () => {
  afterEach(() => {
    mockGetLLMLeaderboard.mockReset()
  })

  it('renders medals for ranks 1-3, the numeric default rank, providers, CI and n/a', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    const { container } = render(<LLMLeaderboardTable />)

    await waitFor(() => {
      expect(container.textContent).toContain('GPT-4o')
    })

    const text = container.textContent || ''
    // Medal emojis for top 3 (getMedalIcon cases 1/2/3)
    expect(text).toContain('🥇')
    expect(text).toContain('🥈')
    expect(text).toContain('🥉')
    // Default branch renders the raw rank number for the 4th row (rank 7).
    expect(text).toContain('7')
    // Provider badges, including the unknown-provider fallback path.
    expect(text).toContain('OpenAI')
    expect(text).toContain('anthropic')
    expect(text).toContain('weird_provider')
    // The no-score entry renders the n/a placeholder.
    expect(text).toContain('n/a')
    // generation_count rendered via toLocaleString for the top row.
    expect(text).toMatch(/1[.,]234/)

    // Default metric (llm_judge_falloesung_grade_points) is unregistered, so
    // getMetricScale falls back to '0-1' and scores render as a percentage.
    expect(text).toMatch(/90\.0%|85\.0%|78\.0%/)
    // CI for the top row (both bounds present) is shown in brackets.
    expect(text).toMatch(/\[.*%.*–.*%.*\]/)

    // Four data rows.
    const rows = container.querySelectorAll('tbody tr')
    expect(rows.length).toBe(4)
  })

  it('renders the empty state when the leaderboard is empty', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(emptyResponse)
    const { container } = render(<LLMLeaderboardTable />)

    await waitFor(() => {
      expect(container.textContent).toContain('leaderboards.llm.noDataTitle')
    })
    expect(container.textContent).toContain('leaderboards.llm.noDataDescription')
    // No pagination when there are zero models.
    expect(screen.queryByLabelText('Pagination')).not.toBeInTheDocument()
  })

  it('shows the error state and refetches when Retry is clicked', async () => {
    mockGetLLMLeaderboard.mockRejectedValueOnce(new Error('Boom failure'))
    // After retry, succeed so the component leaves the error state.
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)

    const { container } = render(<LLMLeaderboardTable />)

    // Error message (error.message) is rendered, plus the retry button.
    await screen.findByText('Boom failure')
    const callsBeforeRetry = mockGetLLMLeaderboard.mock.calls.length

    const retry = screen.getByRole('button', { name: 'leaderboards.retry' })
    await userEvent.click(retry)

    await waitFor(() => {
      expect(mockGetLLMLeaderboard.mock.calls.length).toBeGreaterThan(
        callsBeforeRetry
      )
    })
    // Recovered: data now visible.
    await waitFor(() => {
      expect(container.textContent).toContain('GPT-4o')
    })
  })

  it('renders the available-metrics footer with the "and more" overflow', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    const { container } = render(<LLMLeaderboardTable />)

    await waitFor(() => {
      expect(container.textContent).toContain('leaderboards.llm.availableMetrics')
    })
    // 13 metrics, only first 10 listed -> "and more" with count 3.
    expect(container.textContent).toContain('leaderboards.llm.andMore')
    expect(container.textContent).toContain('metric_0')
    expect(container.textContent).toContain('metric_9')
  })

  it('renders pagination and requests the next page (offset) when navigating', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    render(<LLMLeaderboardTable />)

    await screen.findByText('GPT-4o')

    const nextBtn = screen.getByLabelText('common.pagination.nextPage')
    mockGetLLMLeaderboard.mockClear()
    await userEvent.click(nextBtn)

    await waitFor(() => {
      expect(mockGetLLMLeaderboard).toHaveBeenCalled()
    })
    // Page 2 -> offset = (2-1)*50 = 50.
    const lastCall =
      mockGetLLMLeaderboard.mock.calls[
        mockGetLLMLeaderboard.mock.calls.length - 1
      ][0]
    expect(lastCall.offset).toBe(50)
    expect(lastCall.limit).toBe(50)
  })

  it('changes the time period and re-queries with that period (page reset to 1)', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    render(<LLMLeaderboardTable />)

    await screen.findByText('GPT-4o')
    await openFilterPanel()

    const periodSelect = findSelectByOption('leaderboards.thisMonth')
    mockGetLLMLeaderboard.mockClear()
    await userEvent.selectOptions(periodSelect, 'monthly')

    await waitFor(() => {
      const calls = mockGetLLMLeaderboard.mock.calls
      expect(calls.some((c) => c[0].period === 'monthly')).toBe(true)
    })
    // Page reset to 1 -> offset 0.
    const monthlyCall = mockGetLLMLeaderboard.mock.calls.find(
      (c) => c[0].period === 'monthly'
    )!
    expect(monthlyCall[0].offset).toBe(0)
  })

  it('switches metric to accuracy and re-queries with metric=accuracy', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    render(<LLMLeaderboardTable />)

    await screen.findByText('GPT-4o')
    await openFilterPanel()

    // The metric select includes the registered "Accuracy" option.
    const metricSelect = findSelectByOption('Accuracy')
    mockGetLLMLeaderboard.mockClear()
    await userEvent.selectOptions(metricSelect, 'accuracy')

    await waitFor(() => {
      expect(
        mockGetLLMLeaderboard.mock.calls.some((c) => c[0].metric === 'accuracy')
      ).toBe(true)
    })
  })

  it('switches aggregation to sum for a summable metric and re-queries', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    render(<LLMLeaderboardTable />)

    await screen.findByText('GPT-4o')
    await openFilterPanel()

    // Sum is only offered when the current metric is summable. Switch to
    // accuracy (summable) first so the Sum option appears.
    const metricSelect = findSelectByOption('Accuracy')
    await userEvent.selectOptions(metricSelect, 'accuracy')

    await waitFor(() => {
      const aggSelect = screen.queryAllByRole('combobox').find((sel) =>
        within(sel as HTMLElement)
          .queryAllByRole('option')
          .some((o) => o.textContent === 'leaderboards.aggregation.sum')
      )
      expect(aggSelect).toBeTruthy()
    })

    const aggSelect = findSelectByOption('leaderboards.aggregation.sum')
    mockGetLLMLeaderboard.mockClear()
    await userEvent.selectOptions(aggSelect, 'sum')

    await waitFor(() => {
      expect(
        mockGetLLMLeaderboard.mock.calls.some(
          (c) => c[0].aggregation === 'sum'
        )
      ).toBe(true)
    })
    // In sum mode the score formatter takes the raw-number branch (no %).
    // We can't easily assert the exact glyph through the registry, but the
    // re-query with aggregation=sum confirms the toggle wired through.
  })

  it('toggles the min-samples checkbox so the threshold is sent as 0 and re-queried', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    const { container } = render(<LLMLeaderboardTable />)

    await screen.findByText('GPT-4o')
    await openFilterPanel()

    // First call uses the default ON threshold (50).
    expect(mockGetLLMLeaderboard.mock.calls[0][0].min_generation_count).toBe(50)

    // Locate the min-samples checkbox: it is the one that is checked by
    // default (the include-all checkbox is unchecked + disabled).
    const checkboxes = container.querySelectorAll<HTMLInputElement>(
      'input[type="checkbox"]'
    )
    const minSamples = Array.from(checkboxes).find(
      (c) => c.checked && !c.disabled
    )
    expect(minSamples).toBeTruthy()

    mockGetLLMLeaderboard.mockClear()
    fireEvent.click(minSamples!)

    await waitFor(() => {
      expect(
        mockGetLLMLeaderboard.mock.calls.some(
          (c) => c[0].min_generation_count === 0 && c[0].min_samples_evaluated === 0
        )
      ).toBe(true)
    })
  })

  it('selects a project from the project filter menu and forwards project_ids', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    render(<LLMLeaderboardTable />)

    await screen.findByText('GPT-4o')

    // Open the project filter Menu. Its button shows the "all projects"
    // label by default; clicking it reveals the per-project checkboxes.
    const projectButton = screen.getByText('leaderboards.allProjects')
    await userEvent.click(projectButton)

    // The two mocked projects render as menu items.
    const alpha = await screen.findByText('Project Alpha')
    mockGetLLMLeaderboard.mockClear()
    await userEvent.click(alpha)

    await waitFor(() => {
      expect(
        mockGetLLMLeaderboard.mock.calls.some(
          (c) =>
            Array.isArray(c[0].project_ids) && c[0].project_ids.includes('p1')
        )
      ).toBe(true)
    })
  })

  it('clears all filters back to defaults via the toolbar Clear button', async () => {
    mockGetLLMLeaderboard.mockResolvedValue(dataResponse)
    render(<LLMLeaderboardTable />)

    await screen.findByText('GPT-4o')
    await openFilterPanel()

    // Make a filter active (period change) so Clear has something to reset.
    const periodSelect = findSelectByOption('leaderboards.thisWeek')
    await userEvent.selectOptions(periodSelect, 'weekly')
    await waitFor(() => {
      expect(
        mockGetLLMLeaderboard.mock.calls.some((c) => c[0].period === 'weekly')
      ).toBe(true)
    })

    // The FilterToolbar exposes a clear-all control labeled via clearLabel.
    const clearBtn = screen.getByRole('button', {
      name: 'common.filters.clearAll',
    })
    mockGetLLMLeaderboard.mockClear()
    await userEvent.click(clearBtn)

    await waitFor(() => {
      expect(
        mockGetLLMLeaderboard.mock.calls.some((c) => c[0].period === 'overall')
      ).toBe(true)
    })
  })
})
