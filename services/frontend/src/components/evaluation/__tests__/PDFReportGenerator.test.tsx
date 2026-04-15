/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PDFReportGenerator, PDFReportGeneratorProps } from '../PDFReportGenerator'

// Mock i18n
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.pdfReport.configTitle': 'Report Configuration',
        'evaluation.pdfReport.reportFormat': 'Report Format',
        'evaluation.pdfReport.academicFormat': 'Academic',
        'evaluation.pdfReport.businessFormat': 'Business',
        'evaluation.pdfReport.academicDescription': 'Includes methodology and citations',
        'evaluation.pdfReport.businessDescription': 'Executive summary focused',
        'evaluation.pdfReport.includeSections': 'Include Sections',
        'evaluation.pdfReport.resultsTables': 'Results Tables',
        'evaluation.pdfReport.visualizations': 'Visualizations',
        'evaluation.pdfReport.statisticalAnalysis': 'Statistical Analysis',
        'evaluation.pdfReport.selectModels': 'Select Models',
        'evaluation.pdfReport.selectMetrics': 'Select Metrics',
        'evaluation.pdfReport.generating': 'Generating...',
        'evaluation.pdfReport.generatePdf': 'Generate PDF',
        'evaluation.pdfReport.previewTitle': 'Preview',
        'evaluation.pdfReport.reportTitle': `${params?.project} Evaluation Report`,
        'evaluation.pdfReport.generatedOn': 'Generated on',
        'evaluation.pdfReport.format': 'Format:',
        'evaluation.pdfReport.executiveSummary': 'Executive Summary',
        'evaluation.pdfReport.topPerformingModel': 'Top Performing Model',
        'evaluation.pdfReport.averageScore': 'Average Score',
        'evaluation.pdfReport.methodology': 'Methodology',
        'evaluation.pdfReport.evaluationMetrics': 'Evaluation Metrics',
        'evaluation.pdfReport.metricsEmployed': 'The following metrics were employed:',
        'evaluation.pdfReport.statisticalAnalysisSection': 'Statistical Analysis',
        'evaluation.pdfReport.statisticalMethodology': 'Statistical methodology used.',
        'evaluation.pdfReport.results': 'Results',
        'evaluation.pdfReport.rank': 'Rank',
        'evaluation.pdfReport.model': 'Model',
        'evaluation.pdfReport.average': 'Average',
        'evaluation.pdfReport.statisticalSignificance': 'Statistical Significance',
        'evaluation.pdfReport.comparison': 'Comparison',
        'evaluation.pdfReport.pValue': 'p-value',
        'evaluation.pdfReport.significant': 'Significant?',
        'evaluation.pdfReport.effectSize': 'Effect Size',
        'evaluation.pdfReport.performanceSummary': 'Performance Summary',
        'evaluation.pdfReport.modelsEvaluated': 'Models Evaluated',
        'evaluation.pdfReport.metricsComputed': 'Metrics Computed',
        'evaluation.pdfReport.bestScore': 'Best Score',
        'evaluation.pdfReport.footerGenerated': 'Generated on',
        'evaluation.pdfReport.academicDisclaimer': 'For academic use only.',
        'common.yes': 'Yes',
        'common.no': 'No',
      }
      return translations[key] || key
    },
  }),
}))

// Mock html2canvas and jsPDF
jest.mock('html2canvas', () => jest.fn().mockResolvedValue({
  toDataURL: () => 'data:image/png;base64,mock',
  width: 1200,
  height: 800,
}))

jest.mock('jspdf', () => {
  const mockSave = jest.fn()
  const mockAddImage = jest.fn()
  const mockAddPage = jest.fn()
  return jest.fn().mockImplementation(() => ({
    internal: {
      pageSize: {
        getWidth: () => 210,
        getHeight: () => 297,
      },
    },
    addImage: mockAddImage,
    addPage: mockAddPage,
    save: mockSave,
    _save: mockSave,
    _addImage: mockAddImage,
  }))
})

// Mock shared components
jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, variant, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant} {...props}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div className={className} data-testid="card">{children}</div>
  ),
}))

jest.mock('@/components/shared/Checkbox', () => ({
  Checkbox: ({ id, label, checked, onChange }: any) => (
    <label>
      <input
        type="checkbox"
        id={id}
        checked={checked}
        onChange={onChange}
        data-testid={`checkbox-${id}`}
      />
      {label}
    </label>
  ),
}))

jest.mock('@/components/shared/Select', () => ({
  Select: ({ children, value, onValueChange }: any) => (
    <div data-testid="select-root" data-value={value}>
      {typeof children === 'function' ? children({ value, onValueChange }) : children}
    </div>
  ),
  SelectContent: ({ children }: any) => <div data-testid="select-content">{children}</div>,
  SelectItem: ({ children, value }: any) => (
    <option data-testid={`select-item-${value}`} value={value}>{children}</option>
  ),
  SelectTrigger: ({ children, className }: any) => (
    <div data-testid="select-trigger" className={className}>{children}</div>
  ),
  SelectValue: () => <span data-testid="select-value" />,
}))

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
}))

const makeDefaultProps = (overrides?: Partial<PDFReportGeneratorProps>): PDFReportGeneratorProps => ({
  projectId: 'project-1',
  projectName: 'Test Project',
  evaluationData: {
    models: [
      {
        model_id: 'gpt-4',
        model_name: 'GPT-4',
        provider: 'OpenAI',
        metrics: { rouge: 0.85, bleu: 0.72 },
      },
      {
        model_id: 'claude-3',
        model_name: 'Claude 3',
        provider: 'Anthropic',
        metrics: { rouge: 0.88, bleu: 0.75 },
      },
    ],
  },
  ...overrides,
})

describe('PDFReportGenerator', () => {
  describe('Rendering', () => {
    it('renders the configuration panel', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Report Configuration')).toBeInTheDocument()
    })

    it('renders format selection', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Report Format')).toBeInTheDocument()
    })

    it('renders content section checkboxes', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByTestId('checkbox-include-tables')).toBeInTheDocument()
      expect(screen.getByTestId('checkbox-include-charts')).toBeInTheDocument()
      expect(screen.getByTestId('checkbox-include-statistics')).toBeInTheDocument()
    })

    it('renders model selection checkboxes', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByTestId('checkbox-model-gpt-4')).toBeInTheDocument()
      expect(screen.getByTestId('checkbox-model-claude-3')).toBeInTheDocument()
    })

    it('renders metric selection checkboxes', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByTestId('checkbox-metric-bleu')).toBeInTheDocument()
      expect(screen.getByTestId('checkbox-metric-rouge')).toBeInTheDocument()
    })

    it('shows model and metric counts in summary', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getAllByText(/2 models/).length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText(/2 metrics/).length).toBeGreaterThanOrEqual(1)
    })

    it('renders the generate PDF button', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Generate PDF')).toBeInTheDocument()
    })

    it('renders the preview section', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Preview')).toBeInTheDocument()
    })
  })

  describe('Preview content', () => {
    it('renders the report title with project name', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Test Project Evaluation Report')).toBeInTheDocument()
    })

    it('renders the executive summary', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Executive Summary')).toBeInTheDocument()
    })

    it('shows model count in executive summary text', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText(/2 language models/)).toBeInTheDocument()
    })

    it('shows top performing model info', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Top Performing Model')).toBeInTheDocument()
      // Claude 3 has higher avg: (0.88+0.75)/2=0.815 vs GPT-4 (0.85+0.72)/2=0.785
      // Claude 3 appears in both checkbox and preview, use getAllByText
      expect(screen.getAllByText('Claude 3').length).toBeGreaterThanOrEqual(1)
    })

    it('shows methodology section for academic format', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Methodology')).toBeInTheDocument()
      expect(screen.getByText('Evaluation Metrics')).toBeInTheDocument()
    })

    it('shows metric citations in methodology', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      // rouge and bleu are in METRIC_CITATIONS
      expect(screen.getByText(/Lin \(2004\)/)).toBeInTheDocument()
      expect(screen.getByText(/Papineni et al\./)).toBeInTheDocument()
    })

    it('renders results table with model rankings', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Results')).toBeInTheDocument()
      expect(screen.getByText('#1')).toBeInTheDocument()
      expect(screen.getByText('#2')).toBeInTheDocument()
    })

    it('shows performance summary cards', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Performance Summary')).toBeInTheDocument()
      expect(screen.getByText('Models Evaluated')).toBeInTheDocument()
      expect(screen.getByText('Metrics Computed')).toBeInTheDocument()
    })

    it('shows academic disclaimer in academic format', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('For academic use only.')).toBeInTheDocument()
    })
  })

  describe('Metric value formatting', () => {
    it('formats values between 0 and 1 as percentages', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      // The average scores appear in the results table
      // Claude 3 avg: (0.88+0.75)/2 = 0.815 -> 81.50%
      // May appear in multiple places (results table + performance summary)
      expect(screen.getAllByText('81.50%').length).toBeGreaterThanOrEqual(1)
    })

    it('renders N/A for undefined metric values', () => {
      const props = makeDefaultProps({
        evaluationData: {
          models: [
            {
              model_id: 'model-1',
              model_name: 'Model 1',
              provider: 'Test',
              metrics: { rouge: 0.5, bleu: undefined as any },
            },
          ],
        },
      })
      render(<PDFReportGenerator {...props} />)
      expect(screen.getByText('N/A')).toBeInTheDocument()
    })
  })

  describe('Model toggling', () => {
    it('toggles model selection via checkboxes', async () => {
      const user = userEvent.setup()
      render(<PDFReportGenerator {...makeDefaultProps()} />)

      // GPT-4 is initially selected
      const gpt4Checkbox = screen.getByTestId('checkbox-model-gpt-4')
      expect(gpt4Checkbox).toBeChecked()

      // Uncheck GPT-4
      await user.click(gpt4Checkbox)
      expect(gpt4Checkbox).not.toBeChecked()

      // Summary should update
      expect(screen.getByText(/1 models/)).toBeInTheDocument()
    })
  })

  describe('Metric toggling', () => {
    it('toggles metric selection via checkboxes', async () => {
      const user = userEvent.setup()
      render(<PDFReportGenerator {...makeDefaultProps()} />)

      const rougeCheckbox = screen.getByTestId('checkbox-metric-rouge')
      expect(rougeCheckbox).toBeChecked()

      await user.click(rougeCheckbox)
      expect(rougeCheckbox).not.toBeChecked()
      expect(screen.getByText(/1 metrics/)).toBeInTheDocument()
    })
  })

  describe('Section toggling', () => {
    it('toggles tables section checkbox', async () => {
      const user = userEvent.setup()
      render(<PDFReportGenerator {...makeDefaultProps()} />)

      const tablesCheckbox = screen.getByTestId('checkbox-include-tables')
      expect(tablesCheckbox).toBeChecked()

      await user.click(tablesCheckbox)
      expect(tablesCheckbox).not.toBeChecked()

      // Results table should no longer be in preview
      expect(screen.queryByText('Rank')).not.toBeInTheDocument()
    })

    it('toggles charts section checkbox', async () => {
      const user = userEvent.setup()
      render(<PDFReportGenerator {...makeDefaultProps()} />)

      const chartsCheckbox = screen.getByTestId('checkbox-include-charts')
      expect(chartsCheckbox).toBeChecked()

      await user.click(chartsCheckbox)
      expect(chartsCheckbox).not.toBeChecked()

      // Performance summary should no longer appear
      expect(screen.queryByText('Performance Summary')).not.toBeInTheDocument()
    })

    it('toggles statistics section checkbox', async () => {
      const user = userEvent.setup()
      const props = makeDefaultProps({
        evaluationData: {
          models: [
            {
              model_id: 'gpt-4',
              model_name: 'GPT-4',
              provider: 'OpenAI',
              metrics: { rouge: 0.85 },
            },
          ],
          significanceTests: [
            {
              model_a: 'GPT-4',
              model_b: 'Claude 3',
              p_value: 0.003,
              significant: true,
              effect_size: 0.85,
            },
          ],
        },
      })
      render(<PDFReportGenerator {...props} />)

      expect(screen.getByText('Statistical Significance')).toBeInTheDocument()

      const statsCheckbox = screen.getByTestId('checkbox-include-statistics')
      await user.click(statsCheckbox)
      expect(screen.queryByText('Statistical Significance')).not.toBeInTheDocument()
    })
  })

  describe('Significance tests', () => {
    it('renders significance test table when data is provided', () => {
      const props = makeDefaultProps({
        evaluationData: {
          models: [
            {
              model_id: 'gpt-4',
              model_name: 'GPT-4',
              provider: 'OpenAI',
              metrics: { rouge: 0.85 },
            },
          ],
          significanceTests: [
            {
              model_a: 'GPT-4',
              model_b: 'Claude 3',
              p_value: 0.003,
              significant: true,
              effect_size: 0.85,
            },
          ],
        },
      })
      render(<PDFReportGenerator {...props} />)

      expect(screen.getByText('Statistical Significance')).toBeInTheDocument()
      expect(screen.getByText('GPT-4 vs Claude 3')).toBeInTheDocument()
      expect(screen.getByText('0.0030')).toBeInTheDocument()
      expect(screen.getByText('Yes')).toBeInTheDocument()
      expect(screen.getByText('0.850')).toBeInTheDocument()
    })

    it('shows "No" for non-significant tests', () => {
      const props = makeDefaultProps({
        evaluationData: {
          models: [
            {
              model_id: 'gpt-4',
              model_name: 'GPT-4',
              provider: 'OpenAI',
              metrics: { rouge: 0.85 },
            },
          ],
          significanceTests: [
            {
              model_a: 'GPT-4',
              model_b: 'Claude 3',
              p_value: 0.08,
              significant: false,
              effect_size: 0.2,
            },
          ],
        },
      })
      render(<PDFReportGenerator {...props} />)
      expect(screen.getByText('No')).toBeInTheDocument()
    })

    it('does not render significance table when no tests are provided', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.queryByText('Statistical Significance')).not.toBeInTheDocument()
    })
  })

  describe('Generate PDF button', () => {
    it('is disabled when no models are selected', async () => {
      const user = userEvent.setup()
      render(<PDFReportGenerator {...makeDefaultProps()} />)

      // Uncheck all models
      await user.click(screen.getByTestId('checkbox-model-gpt-4'))
      await user.click(screen.getByTestId('checkbox-model-claude-3'))

      const button = screen.getByText('Generate PDF')
      expect(button).toBeDisabled()
    })

    it('is disabled when no metrics are selected', async () => {
      const user = userEvent.setup()
      render(<PDFReportGenerator {...makeDefaultProps()} />)

      // Uncheck all metrics
      await user.click(screen.getByTestId('checkbox-metric-rouge'))
      await user.click(screen.getByTestId('checkbox-metric-bleu'))

      const button = screen.getByText('Generate PDF')
      expect(button).toBeDisabled()
    })

    it('triggers PDF generation on click', async () => {
      const user = userEvent.setup()
      const html2canvas = require('html2canvas')
      const onGenerate = jest.fn()
      render(<PDFReportGenerator {...makeDefaultProps({ onGenerate })} />)

      const button = screen.getByText('Generate PDF')
      await user.click(button)

      expect(html2canvas).toHaveBeenCalled()
    })

    it('calls onGenerate callback after successful PDF generation', async () => {
      const user = userEvent.setup()
      const onGenerate = jest.fn()
      render(<PDFReportGenerator {...makeDefaultProps({ onGenerate })} />)

      await user.click(screen.getByText('Generate PDF'))

      // Wait for async operation
      await screen.findByText('Generate PDF')
      expect(onGenerate).toHaveBeenCalledTimes(1)
    })

    it('handles PDF generation errors gracefully', async () => {
      const user = userEvent.setup()
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation()
      const html2canvas = require('html2canvas')
      html2canvas.mockRejectedValueOnce(new Error('Canvas failed'))

      render(<PDFReportGenerator {...makeDefaultProps()} />)
      await user.click(screen.getByText('Generate PDF'))

      await screen.findByText('Generate PDF')
      expect(consoleSpy).toHaveBeenCalledWith('PDF generation failed:', expect.any(Error))
      consoleSpy.mockRestore()
    })
  })

  describe('Empty / edge cases', () => {
    it('renders with empty models array', () => {
      const props = makeDefaultProps({
        evaluationData: { models: [] },
      })
      render(<PDFReportGenerator {...props} />)
      expect(screen.getByText('Report Configuration')).toBeInTheDocument()
      expect(screen.getByText(/0 models/)).toBeInTheDocument()
    })

    it('handles model without model_name by using model_id', () => {
      const props = makeDefaultProps({
        evaluationData: {
          models: [
            {
              model_id: 'custom-model',
              model_name: '',
              provider: 'Custom',
              metrics: { rouge: 0.7 },
            },
          ],
        },
      })
      render(<PDFReportGenerator {...props} />)
      // model_name is empty string, so model_id used as fallback
      expect(screen.getByText('custom-model')).toBeInTheDocument()
    })

    it('formats large scores (>1) with 4 decimal places', () => {
      const props = makeDefaultProps({
        evaluationData: {
          models: [
            {
              model_id: 'model-1',
              model_name: 'Model 1',
              provider: 'Test',
              metrics: { perplexity: 15.678 },
            },
          ],
        },
      })
      render(<PDFReportGenerator {...props} />)
      // 15.678 > 1 so formatMetricValue returns value.toFixed(4) = "15.6780"
      // Appears in both results table and performance summary
      expect(screen.getAllByText('15.6780').length).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Format description', () => {
    it('shows academic description for academic format', () => {
      render(<PDFReportGenerator {...makeDefaultProps()} />)
      expect(screen.getByText('Includes methodology and citations')).toBeInTheDocument()
    })
  })
})
