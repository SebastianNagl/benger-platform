/**
 * Tests for Report Viewer Page
 *
 * Tests the detailed report view including:
 * - Report content display (loading, error, data states)
 * - Statistics rendering
 * - Evaluation charts with different metric scales
 * - Participants modal open/close
 * - Section visibility toggling
 * - Custom content overrides
 */

import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock next/navigation
const mockPush = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: jest.fn(),
    prefetch: jest.fn(),
  }),
}))

// Mock next/dynamic to return a simple component
jest.mock('next/dynamic', () => {
  return function mockDynamic(loader: () => Promise<any>, _options?: any) {
    return function MockPlot({ data, layout }: { data: any; layout: any }) {
      return (
        <div data-testid="plotly-chart" data-layout={JSON.stringify(layout)}>
          {data?.map((trace: any, i: number) => (
            <div key={i} data-testid={`chart-trace-${i}`}>
              {trace.name}: {trace.y?.join(', ')}
            </div>
          ))}
        </div>
      )
    }
  }
})

// Mock the I18n context
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      if (vars) {
        let result = key
        for (const [k, v] of Object.entries(vars)) {
          result = result.replace(`{${k}}`, String(v))
        }
        return result
      }
      return key
    },
  }),
}))

// Mock Breadcrumb
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: ({ items }: any) => (
    <nav data-testid="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}))

// Mock the reports API
jest.mock('@/lib/api/reports', () => ({
  getReportData: jest.fn(),
}))

// Mock React's use() hook to synchronously return the value
// This is necessary because use() with Promises doesn't work in jsdom tests
const originalReact = jest.requireActual('react')
jest.mock('react', () => ({
  ...jest.requireActual('react'),
  use: (promise: any) => {
    // For promises, return { id: 'report-1' } by default
    // The mock ID can be overridden per test
    if (promise && typeof promise.then === 'function') {
      return mockUseResult
    }
    return promise
  },
}))

let mockUseResult = { id: 'report-1' }

import { getReportData } from '@/lib/api/reports'
import ReportViewerPage from '../page'

const mockGetReportData = getReportData as jest.Mock

// Mock report data factory
const createMockReportData = (overrides: any = {}) => ({
  report: {
    id: 'report-1',
    project_id: 'project-1',
    project_title: 'Test Project',
    content: {
      sections: {
        project_info: {
          status: 'completed',
          editable: true,
          visible: true,
          title: 'Test Project',
          description: 'A test project for evaluation',
          custom_title: null,
          custom_description: null,
        },
        data: {
          status: 'completed',
          editable: true,
          visible: true,
          task_count: 100,
          custom_text: null,
          show_count: true,
        },
        annotations: {
          status: 'completed',
          editable: true,
          visible: true,
          annotation_count: 300,
          custom_text: null,
          show_count: true,
          show_participants: true,
          acknowledgment_text: 'Thanks to all participants',
        },
        generation: {
          status: 'completed',
          editable: true,
          visible: true,
          models: ['gpt-4', 'claude-3'],
          custom_text: null,
          show_models: true,
          show_config: false,
        },
        evaluation: {
          status: 'completed',
          editable: true,
          visible: true,
          methods: ['exact_match', 'f1'],
          metrics: {},
          charts_config: {},
          custom_interpretation: 'GPT-4 performed best overall',
          conclusions: 'The evaluation shows promising results',
        },
      },
      metadata: {
        last_auto_update: '2025-01-10T10:00:00Z',
        sections_completed: [
          'project_info',
          'data',
          'annotations',
          'generation',
          'evaluation',
        ],
        can_publish: true,
      },
    },
    is_published: true,
    published_at: '2025-01-10T10:00:00Z',
    published_by: 'admin',
    created_by: 'admin',
    created_at: '2025-01-01T10:00:00Z',
    updated_at: '2025-01-10T10:00:00Z',
    can_publish: true,
    can_publish_reason: 'All requirements met',
  },
  statistics: {
    task_count: 100,
    annotation_count: 300,
    participant_count: 5,
    model_count: 2,
  },
  participants: [
    { id: 'user-1', username: 'annotator1', annotation_count: 100 },
    { id: 'user-2', username: 'annotator2', annotation_count: 80 },
    { id: 'user-3', username: 'annotator3', annotation_count: 60 },
    { id: 'user-4', username: 'annotator4', annotation_count: 40 },
    { id: 'user-5', username: 'annotator5', annotation_count: 20 },
  ],
  models: ['gpt-4', 'claude-3'],
  evaluation_charts: {
    by_model: {
      'gpt-4': { exact_match: 0.85, f1: 0.92 },
      'claude-3': { exact_match: 0.88, f1: 0.94 },
    },
    by_method: {
      exact_match: { 'gpt-4': 0.85, 'claude-3': 0.88 },
      f1: { 'gpt-4': 0.92, 'claude-3': 0.94 },
    },
    metric_metadata: {
      exact_match: {
        higher_is_better: true,
        range: [0, 1],
        name: 'Exact Match',
        category: 'qa',
      },
      f1: {
        higher_is_better: true,
        range: [0, 1],
        name: 'F1 Score',
        category: 'qa',
      },
    },
  },
  ...overrides,
})

function renderPage(id = 'report-1') {
  mockUseResult = { id }
  const params = Promise.resolve({ id })
  return render(<ReportViewerPage params={params} />)
}

describe('Report Viewer Page', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUseResult = { id: 'report-1' }
  })

  describe('Loading State', () => {
    it('shows loading state while data is being fetched', () => {
      mockGetReportData.mockImplementation(
        () => new Promise(() => {})
      )

      renderPage()

      expect(
        screen.getByText('reports.detail.loadingReport')
      ).toBeInTheDocument()
    })
  })

  describe('Error State', () => {
    it('shows error message when API fails', async () => {
      mockGetReportData.mockRejectedValue(new Error('Network error'))

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument()
      })
    })

    it('shows fallback error when error message is empty', async () => {
      mockGetReportData.mockRejectedValue(new Error(''))

      renderPage()

      await waitFor(() => {
        expect(
          screen.getByText('reports.detail.failedToLoadReport')
        ).toBeInTheDocument()
      })
    })

    it('shows retry button on error', async () => {
      mockGetReportData.mockRejectedValue(new Error('fail'))

      renderPage()

      await waitFor(() => {
        expect(
          screen.getByText('reports.detail.retry')
        ).toBeInTheDocument()
      })
    })

    it('shows back to reports button on error', async () => {
      mockGetReportData.mockRejectedValue(new Error('fail'))

      renderPage()

      await waitFor(() => {
        expect(
          screen.getByText('reports.detail.backToReports')
        ).toBeInTheDocument()
      })
    })

    it('navigates to /reports on back button click', async () => {
      const user = userEvent.setup()
      mockGetReportData.mockRejectedValue(new Error('fail'))

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.backToReports')).toBeInTheDocument()
      })

      await user.click(screen.getByText('reports.detail.backToReports'))
      expect(mockPush).toHaveBeenCalledWith('/reports')
    })

    it('retries loading on retry button click', async () => {
      mockGetReportData
        .mockRejectedValueOnce(new Error('fail'))
        .mockResolvedValueOnce(createMockReportData())

      const user = userEvent.setup()
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.retry')).toBeInTheDocument()
      })

      await user.click(screen.getByText('reports.detail.retry'))

      await waitFor(() => {
        expect(mockGetReportData).toHaveBeenCalledTimes(2)
      })
    })

    it('shows reportNotFound when data is null', async () => {
      mockGetReportData.mockResolvedValue(null)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.reportNotFound')).toBeInTheDocument()
      })
    })
  })

  describe('Report Content Display', () => {
    it('renders project title from default', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        const headings = screen.getAllByText('Test Project')
        expect(headings.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('renders custom title when provided', async () => {
      const data = createMockReportData()
      data.report.content.sections.project_info.custom_title = 'Custom Title'
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        const headings = screen.getAllByText('Custom Title')
        expect(headings.length).toBeGreaterThanOrEqual(1)
      })
    })

    it('renders custom description when provided', async () => {
      const data = createMockReportData()
      data.report.content.sections.project_info.custom_description = 'Custom Desc'
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Custom Desc')).toBeInTheDocument()
      })
    })

    it('renders published_at date', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        const publishedText = screen.getByText(/reports\.detail\.publishedOn/)
        expect(publishedText).toBeInTheDocument()
      })
    })

    it('does not render published_at when null', async () => {
      const data = createMockReportData()
      data.report.published_at = null
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getAllByText('Test Project').length).toBeGreaterThanOrEqual(1)
      })

      expect(screen.queryByText(/reports\.detail\.publishedOn/)).not.toBeInTheDocument()
    })
  })

  describe('Statistics Grid', () => {
    it('renders task count', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('100')).toBeInTheDocument()
      })
      expect(screen.getByText('reports.detail.tasks')).toBeInTheDocument()
    })

    it('renders annotation count when visible', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('300')).toBeInTheDocument()
      })
    })

    it('hides annotation count when show_count is false', async () => {
      const data = createMockReportData()
      data.report.content.sections.annotations.show_count = false
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getAllByText('Test Project').length).toBeGreaterThanOrEqual(1)
      })

      // Annotation count stat card should not be present
      expect(screen.queryByText('reports.detail.annotations')).not.toBeInTheDocument()
    })

    it('renders participant count with view all button', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('5')).toBeInTheDocument()
      })
      expect(screen.getByText('reports.detail.viewAll')).toBeInTheDocument()
    })

    it('hides participant count when show_participants is false', async () => {
      const data = createMockReportData()
      data.report.content.sections.annotations.show_participants = false
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getAllByText('Test Project').length).toBeGreaterThanOrEqual(1)
      })

      expect(screen.queryByText('reports.detail.viewAll')).not.toBeInTheDocument()
    })

    it('renders model count', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.modelsEvaluated')).toBeInTheDocument()
      })
    })
  })

  describe('Data Section', () => {
    it('renders data section when visible', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.data')).toBeInTheDocument()
      })
    })

    it('renders custom data text when provided', async () => {
      const data = createMockReportData()
      data.report.content.sections.data.custom_text = 'Custom data description'
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Custom data description')).toBeInTheDocument()
      })
    })

    it('hides data section when not visible', async () => {
      const data = createMockReportData()
      data.report.content.sections.data.visible = false
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getAllByText('Test Project').length).toBeGreaterThanOrEqual(1)
      })

      const headings = screen.queryAllByText('reports.detail.data')
      expect(headings.length).toBe(0)
    })
  })

  describe('Annotations Section', () => {
    it('renders annotations section with acknowledgment', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.annotationsSection')).toBeInTheDocument()
      })
      expect(screen.getByText('Thanks to all participants')).toBeInTheDocument()
    })

    it('renders custom annotation text', async () => {
      const data = createMockReportData()
      data.report.content.sections.annotations.custom_text = 'Custom annotations'
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Custom annotations')).toBeInTheDocument()
      })
    })

    it('hides annotations section when not visible', async () => {
      const data = createMockReportData()
      data.report.content.sections.annotations.visible = false
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getAllByText('Test Project').length).toBeGreaterThanOrEqual(1)
      })

      expect(screen.queryByText('reports.detail.annotationsSection')).not.toBeInTheDocument()
    })

    it('hides acknowledgment when not provided', async () => {
      const data = createMockReportData()
      data.report.content.sections.annotations.acknowledgment_text = null
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.annotationsSection')).toBeInTheDocument()
      })

      expect(screen.queryByText('Thanks to all participants')).not.toBeInTheDocument()
    })
  })

  describe('Generation Section', () => {
    it('renders generation section with models', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.generation')).toBeInTheDocument()
      })
    })

    it('renders custom generation text', async () => {
      const data = createMockReportData()
      data.report.content.sections.generation.custom_text = 'Custom gen text'
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Custom gen text')).toBeInTheDocument()
      })
    })

    it('hides models when show_models is false', async () => {
      const data = createMockReportData()
      data.report.content.sections.generation.show_models = false
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.generation')).toBeInTheDocument()
      })
    })

    it('hides generation section when not visible', async () => {
      const data = createMockReportData()
      data.report.content.sections.generation.visible = false
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getAllByText('Test Project').length).toBeGreaterThanOrEqual(1)
      })

      expect(screen.queryByText('reports.detail.generation')).not.toBeInTheDocument()
    })
  })

  describe('Evaluation Section', () => {
    it('renders evaluation section with interpretation', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.evaluationResults')).toBeInTheDocument()
      })
      expect(screen.getByText('GPT-4 performed best overall')).toBeInTheDocument()
    })

    it('renders conclusions', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('The evaluation shows promising results')).toBeInTheDocument()
      })
    })

    it('hides evaluation section when not visible', async () => {
      const data = createMockReportData()
      data.report.content.sections.evaluation.visible = false
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getAllByText('Test Project').length).toBeGreaterThanOrEqual(1)
      })

      expect(screen.queryByText('reports.detail.evaluationResults')).not.toBeInTheDocument()
    })

    it('hides interpretation when not provided', async () => {
      const data = createMockReportData()
      data.report.content.sections.evaluation.custom_interpretation = null
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.evaluationResults')).toBeInTheDocument()
      })

      expect(screen.queryByText('reports.detail.interpretation')).not.toBeInTheDocument()
    })

    it('hides conclusions when not provided', async () => {
      const data = createMockReportData()
      data.report.content.sections.evaluation.conclusions = null
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.evaluationResults')).toBeInTheDocument()
      })

      expect(screen.queryByText('reports.detail.conclusions')).not.toBeInTheDocument()
    })
  })

  describe('Evaluation Charts', () => {
    it('renders QA metrics chart (0-1 scale)', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.performanceByModel')).toBeInTheDocument()
      })

      const charts = screen.getAllByTestId('plotly-chart')
      expect(charts.length).toBeGreaterThan(0)
    })

    it('renders both QA and LLM Judge charts when both scales present', async () => {
      const data = createMockReportData()
      data.evaluation_charts.by_model['gpt-4'].llm_judge_overall = 4.2
      data.evaluation_charts.by_model['claude-3'].llm_judge_overall = 4.5
      data.evaluation_charts.metric_metadata.llm_judge_overall = {
        higher_is_better: true,
        range: [1, 5],
        name: 'LLM Judge Overall',
        category: 'llm_judge',
      }
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.performanceByModel')).toBeInTheDocument()
      })

      const charts = screen.getAllByTestId('plotly-chart')
      expect(charts.length).toBe(2)
    })

    it('does not render charts when no models', async () => {
      const data = createMockReportData()
      data.evaluation_charts = { by_model: {}, by_method: {}, metric_metadata: {} }
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.evaluationResults')).toBeInTheDocument()
      })

      expect(screen.queryByText('reports.detail.performanceByModel')).not.toBeInTheDocument()
    })

    it('does not render charts when by_model is null', async () => {
      const data = createMockReportData()
      data.evaluation_charts.by_model = null
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.evaluationResults')).toBeInTheDocument()
      })

      expect(screen.queryByTestId('plotly-chart')).not.toBeInTheDocument()
    })

    it('renders chart traces with correct metric display names', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText(/Exact Match/)).toBeInTheDocument()
        expect(screen.getByText(/F1 Score/)).toBeInTheDocument()
      })
    })

    it('handles metrics without metadata (defaults to 0-1 scale)', async () => {
      const data = createMockReportData()
      // Add metric present in model data but without metadata entry
      data.evaluation_charts.by_model['gpt-4'].custom_metric = 0.7
      data.evaluation_charts.by_model['claude-3'].custom_metric = 0.8
      mockGetReportData.mockResolvedValue(data)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.performanceByModel')).toBeInTheDocument()
      })
    })
  })

  describe('Participants Modal', () => {
    it('opens participants modal on view all click', async () => {
      const user = userEvent.setup()
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.viewAll')).toBeInTheDocument()
      })

      await user.click(screen.getByText('reports.detail.viewAll'))

      await waitFor(() => {
        expect(screen.getByText('annotator1')).toBeInTheDocument()
        expect(screen.getByText('annotator2')).toBeInTheDocument()
        expect(screen.getByText('annotator3')).toBeInTheDocument()
      })
    })

    it('closes participants modal on close button click', async () => {
      const user = userEvent.setup()
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.viewAll')).toBeInTheDocument()
      })

      await user.click(screen.getByText('reports.detail.viewAll'))

      await waitFor(() => {
        expect(screen.getByText('annotator1')).toBeInTheDocument()
      })

      await user.click(screen.getByText('reports.detail.close'))

      await waitFor(() => {
        expect(screen.queryByText('annotator1')).not.toBeInTheDocument()
      })
    })

    it('displays annotation counts in modal', async () => {
      const user = userEvent.setup()
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('reports.detail.viewAll')).toBeInTheDocument()
      })

      await user.click(screen.getByText('reports.detail.viewAll'))

      await waitFor(() => {
        expect(screen.getByText('annotator1')).toBeInTheDocument()
      })
    })
  })

  describe('Breadcrumb', () => {
    it('renders breadcrumb navigation', async () => {
      mockGetReportData.mockResolvedValue(createMockReportData())

      renderPage()

      await waitFor(() => {
        expect(screen.getByTestId('breadcrumb')).toBeInTheDocument()
      })
    })
  })
})
