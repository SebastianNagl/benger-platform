/**
 * @jest-environment jsdom
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MetricParameterInput } from '../MetricParameterInput'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      const translations: Record<string, string> = {
        'evaluation.metricParams.hide': 'Hide',
        'evaluation.metricParams.show': 'Show',
        'evaluation.metricParams.advancedParameters': 'Advanced Parameters',
        'evaluation.metricParams.configure': `Configure ${params?.metric}`,
        'evaluation.metricParams.resetToDefaults': 'Reset to Defaults',
        'evaluation.metricParams.bleu.maxNgramOrder': 'Max N-gram Order',
        'evaluation.metricParams.bleu.maxNgramOrderHelp': 'Highest n-gram order',
        'evaluation.metricParams.bleu.smoothingMethod': 'Smoothing Method',
        'evaluation.metricParams.bleu.smoothingMethodHelp': 'Method for smoothing',
        'evaluation.metricParams.bleu.ngram1': 'Unigrams (1)',
        'evaluation.metricParams.bleu.ngram2': 'Bigrams (2)',
        'evaluation.metricParams.bleu.ngram3': 'Trigrams (3)',
        'evaluation.metricParams.bleu.ngram4': '4-grams (4)',
        'evaluation.metricParams.bleu.smoothing1': 'Method 1',
        'evaluation.metricParams.bleu.smoothing2': 'Method 2',
        'evaluation.metricParams.bleu.smoothing3': 'Method 3',
        'evaluation.metricParams.bleu.smoothing4': 'Method 4',
        'evaluation.metricParams.rouge.variant': 'ROUGE Variant',
        'evaluation.metricParams.rouge.variantHelp': 'Variant help',
        'evaluation.metricParams.rouge.rouge1': 'ROUGE-1',
        'evaluation.metricParams.rouge.rouge2': 'ROUGE-2',
        'evaluation.metricParams.rouge.rougeL': 'ROUGE-L',
        'evaluation.metricParams.rouge.rougeLsum': 'ROUGE-Lsum',
        'evaluation.metricParams.rouge.enableStemming': 'Enable Stemming',
        'evaluation.metricParams.rouge.enableStemmingHelp': 'Stemming help',
        'evaluation.metricParams.meteor.alpha': 'Alpha',
        'evaluation.metricParams.meteor.alphaHelp': 'Alpha help',
        'evaluation.metricParams.meteor.beta': 'Beta',
        'evaluation.metricParams.meteor.betaHelp': 'Beta help',
        'evaluation.metricParams.meteor.gamma': 'Gamma',
        'evaluation.metricParams.meteor.gammaHelp': 'Gamma help',
        'evaluation.metricParams.chrf.charOrder': 'Char Order',
        'evaluation.metricParams.chrf.charOrderHelp': 'Char order help',
        'evaluation.metricParams.chrf.charOrder6': '6 (default)',
        'evaluation.metricParams.chrf.wordOrder': 'Word Order',
        'evaluation.metricParams.chrf.wordOrderHelp': 'Word order help',
        'evaluation.metricParams.chrf.wordOrder0': 'chrF (0)',
        'evaluation.metricParams.chrf.wordOrder1': 'chrF+ (1)',
        'evaluation.metricParams.chrf.wordOrder2': 'chrF++ (2)',
        'evaluation.metricParams.chrf.beta': 'Beta',
        'evaluation.metricParams.chrf.betaHelp': 'Beta help',
        'evaluation.metricParams.chrf.beta1': 'F1 (1)',
        'evaluation.metricParams.chrf.beta2': 'F2 (2)',
        'evaluation.metricParams.chrf.beta3': 'F3 (3)',
      }
      return translations[key] || key
    },
  }),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, className }: any) => (
    <button onClick={onClick} className={className}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Input', () => ({
  Input: (props: any) => <input {...props} />,
}))

jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, ...props }: any) => <label {...props}>{children}</label>,
}))

jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({ children }: any) => <>{children}</>,
}))

describe('MetricParameterInput', () => {
  const defaultProps = {
    metric: 'bleu',
    parameters: {},
    onChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Unsupported metrics', () => {
    it('returns null for unsupported metrics', () => {
      const { container } = render(
        <MetricParameterInput
          metric="accuracy"
          parameters={{}}
          onChange={jest.fn()}
        />
      )
      expect(container.firstChild).toBeNull()
    })

    it('returns null for custom metrics', () => {
      const { container } = render(
        <MetricParameterInput
          metric="custom_metric"
          parameters={{}}
          onChange={jest.fn()}
        />
      )
      expect(container.firstChild).toBeNull()
    })
  })

  describe('Toggle visibility', () => {
    it('initially hides advanced parameters', () => {
      render(<MetricParameterInput {...defaultProps} />)
      expect(screen.queryByText('Configure BLEU')).not.toBeInTheDocument()
    })

    it('shows advanced parameters on click', async () => {
      const user = userEvent.setup()
      render(<MetricParameterInput {...defaultProps} />)

      await user.click(screen.getByText(/Show/))

      expect(screen.getByText('Configure BLEU')).toBeInTheDocument()
    })

    it('hides advanced parameters on second click', async () => {
      const user = userEvent.setup()
      render(<MetricParameterInput {...defaultProps} />)

      await user.click(screen.getByText(/Show/))
      expect(screen.getByText('Configure BLEU')).toBeInTheDocument()

      await user.click(screen.getByText(/Hide/))
      expect(screen.queryByText('Configure BLEU')).not.toBeInTheDocument()
    })
  })

  describe('BLEU parameters', () => {
    it('shows n-gram order selector', async () => {
      const user = userEvent.setup()
      render(<MetricParameterInput {...defaultProps} />)

      await user.click(screen.getByText(/Show/))

      expect(screen.getByText('Max N-gram Order')).toBeInTheDocument()
      expect(screen.getByText('4-grams (4)')).toBeInTheDocument()
    })

    it('shows smoothing method selector', async () => {
      const user = userEvent.setup()
      render(<MetricParameterInput {...defaultProps} />)

      await user.click(screen.getByText(/Show/))

      expect(screen.getByText('Smoothing Method')).toBeInTheDocument()
    })

    it('calls onChange when n-gram order changes', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={onChange}
        />
      )

      await user.click(screen.getByText(/Show/))

      // Find the n-gram order select near its label
      const label = screen.getByText('Max N-gram Order')
      const select = label.closest('div')?.parentElement?.querySelector('select') as HTMLSelectElement
      expect(select).toBeTruthy()
      await user.selectOptions(select, '2')

      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ max_order: 2 })
      )
    })
  })

  describe('ROUGE parameters', () => {
    it('shows ROUGE variant selector', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={jest.fn()}
        />
      )

      await user.click(screen.getByText(/Show/))

      expect(screen.getByText('ROUGE Variant')).toBeInTheDocument()
    })

    it('shows stemming toggle', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={jest.fn()}
        />
      )

      await user.click(screen.getByText(/Show/))

      expect(screen.getByText('Enable Stemming')).toBeInTheDocument()
    })
  })

  describe('METEOR parameters', () => {
    it('shows alpha, beta, gamma inputs', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={jest.fn()}
        />
      )

      await user.click(screen.getByText(/Show/))

      expect(screen.getByText('Alpha')).toBeInTheDocument()
      expect(screen.getByText('Beta')).toBeInTheDocument()
      expect(screen.getByText('Gamma')).toBeInTheDocument()
    })
  })

  describe('chrF parameters', () => {
    it('shows char order and word order selectors', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={jest.fn()}
        />
      )

      await user.click(screen.getByText(/Show/))

      expect(screen.getByText('Char Order')).toBeInTheDocument()
      expect(screen.getByText('Word Order')).toBeInTheDocument()
    })
  })

  describe('Reset to defaults', () => {
    it('calls onChange with default values', async () => {
      const user = userEvent.setup()
      const onChange = jest.fn()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{ max_order: 2, smoothing: 'method3' }}
          onChange={onChange}
        />
      )

      await user.click(screen.getByText(/Show/))
      await user.click(screen.getByText('Reset to Defaults'))

      expect(onChange).toHaveBeenCalledWith({
        max_order: 4,
        weights: [0.25, 0.25, 0.25, 0.25],
        smoothing: 'method1',
      })
    })
  })
})
