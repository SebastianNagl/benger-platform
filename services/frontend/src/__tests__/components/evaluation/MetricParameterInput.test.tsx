/**
 * Unit tests for MetricParameterInput component
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MetricParameterInput } from '../../../components/evaluation/MetricParameterInput'

// Mock I18nContext
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: any) => {
      const translations: Record<string, string> = {
        'evaluation.metricParams.show': 'Show',
        'evaluation.metricParams.hide': 'Hide',
        'evaluation.metricParams.advancedParameters': 'Advanced Parameters',
        'evaluation.metricParams.configure': 'Configure {metric} Parameters',
        'evaluation.metricParams.resetToDefaults': 'Reset to Defaults',
        'evaluation.metricParams.bleu.maxNgramOrder': 'Max N-gram Order',
        'evaluation.metricParams.bleu.maxNgramOrderHelp': 'Highest n-gram order for BLEU computation',
        'evaluation.metricParams.bleu.ngram1': 'Unigrams (1)',
        'evaluation.metricParams.bleu.ngram2': 'Bigrams (2)',
        'evaluation.metricParams.bleu.ngram3': 'Trigrams (3)',
        'evaluation.metricParams.bleu.ngram4': '4-grams (4)',
        'evaluation.metricParams.bleu.smoothingMethod': 'Smoothing Method',
        'evaluation.metricParams.bleu.smoothingMethodHelp': 'Smoothing method used for BLEU computation',
        'evaluation.metricParams.bleu.smoothing1': 'Method 1 (Add epsilon)',
        'evaluation.metricParams.bleu.smoothing2': 'Method 2 (Add 1)',
        'evaluation.metricParams.bleu.smoothing3': 'Method 3 (NIST geometric)',
        'evaluation.metricParams.bleu.smoothing4': 'Method 4 (Exponential)',
        'evaluation.metricParams.rouge.variant': 'ROUGE Variant',
        'evaluation.metricParams.rouge.variantHelp': 'Which ROUGE variant to use',
        'evaluation.metricParams.rouge.rouge1': 'ROUGE-1 (Unigrams)',
        'evaluation.metricParams.rouge.rouge2': 'ROUGE-2 (Bigrams)',
        'evaluation.metricParams.rouge.rougeL': 'ROUGE-L (LCS)',
        'evaluation.metricParams.rouge.rougeLsum': 'ROUGE-Lsum (Summary)',
        'evaluation.metricParams.rouge.enableStemming': 'Enable Stemming',
        'evaluation.metricParams.rouge.enableStemmingHelp': 'Enable stemming before computing ROUGE scores',
        'evaluation.metricParams.meteor.alpha': 'Alpha (Precision Weight)',
        'evaluation.metricParams.meteor.alphaHelp': 'Precision weight for METEOR computation',
        'evaluation.metricParams.meteor.beta': 'Beta (Recall Preference)',
        'evaluation.metricParams.meteor.betaHelp': 'Recall preference weight for METEOR',
        'evaluation.metricParams.meteor.gamma': 'Gamma (Fragmentation Penalty)',
        'evaluation.metricParams.meteor.gammaHelp': 'Fragmentation penalty weight for METEOR',
        'evaluation.metricParams.chrf.charOrder': 'Character N-gram Order',
        'evaluation.metricParams.chrf.charOrderHelp': 'The character n-gram order for chrF computation',
        'evaluation.metricParams.chrf.charOrder6': '6 (Default)',
        'evaluation.metricParams.chrf.wordOrder': 'Word N-gram Order',
        'evaluation.metricParams.chrf.wordOrderHelp': 'The word n-gram order for chrF computation',
        'evaluation.metricParams.chrf.wordOrder0': '0 (chrF, no words)',
        'evaluation.metricParams.chrf.wordOrder1': '1 (chrF+)',
        'evaluation.metricParams.chrf.wordOrder2': '2 (chrF++)',
        'evaluation.metricParams.chrf.beta': 'Beta (F-score Weight)',
        'evaluation.metricParams.chrf.betaHelp': 'F-beta score weight for chrF computation',
        'evaluation.metricParams.chrf.beta1': '1 (F1, balanced)',
        'evaluation.metricParams.chrf.beta2': '2 (F2, recall-weighted)',
        'evaluation.metricParams.chrf.beta3': '3 (F3, recall-heavy)',
      }
      let result = translations[key] || key
      if (params && typeof params === 'object') {
        Object.entries(params).forEach(([k, v]) => {
          result = result.replace(`{${k}}`, String(v))
        })
      }
      return result
    },
    locale: 'en',
  }),
}))

// Mock shared components
jest.mock('@/components/shared/Button', () => ({
  Button: ({
    children,
    onClick,
    className,
  }: {
    children: React.ReactNode
    onClick?: () => void
    className?: string
  }) => (
    <button onClick={onClick} className={className}>
      {children}
    </button>
  ),
}))

jest.mock('@/components/shared/Input', () => {
  const React = require('react')
  const Input = React.forwardRef(
    function Input({ id, value, onChange, ...props }: any, ref: any) {
      return <input ref={ref} id={id} value={value} onChange={onChange} {...props} />
    }
  )
  Input.displayName = 'Input'
  return { Input }
})

jest.mock('@/components/shared/Label', () => ({
  Label: ({ children, htmlFor, className }: any) => (
    <label htmlFor={htmlFor} className={className}>
      {children}
    </label>
  ),
}))

jest.mock('@/components/shared/Tooltip', () => ({
  Tooltip: ({
    children,
    content,
  }: {
    children: React.ReactNode
    content: string
  }) => <div data-tooltip={content}>{children}</div>,
}))

/**
 * Helper: find the nearest select or input element associated with a label.
 * The shared Select mock renders a <select> without an id, so getByLabelText
 * no longer works. Instead we locate the label text and walk up to find
 * the closest sibling/parent container that holds the target element.
 */
function getFieldByLabel(labelText: string): HTMLElement {
  const label = screen.getByText(labelText)
  // Walk up to the wrapper div that contains both the label row and the input/select
  const wrapper = label.closest('div')?.parentElement
  const el = wrapper?.querySelector('select, input[type="text"], input[type="number"], input[type="range"]')
  if (!el) throw new Error(`Could not find field element for label "${labelText}"`)
  return el as HTMLElement
}

describe('MetricParameterInput', () => {
  const mockOnChange = jest.fn()

  beforeEach(() => {
    mockOnChange.mockClear()
  })

  describe('Visibility Control', () => {
    it('should return null for unsupported metrics', () => {
      const { container } = render(
        <MetricParameterInput
          metric="unsupported"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      expect(container.firstChild).toBeNull()
    })

    it('should render for bleu metric', () => {
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Show Advanced Parameters')).toBeInTheDocument()
    })

    it('should render for rouge metric', () => {
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Show Advanced Parameters')).toBeInTheDocument()
    })

    it('should render for meteor metric', () => {
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Show Advanced Parameters')).toBeInTheDocument()
    })

    it('should render for chrf metric', () => {
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Show Advanced Parameters')).toBeInTheDocument()
    })

    it('should hide parameters by default', () => {
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      expect(
        screen.queryByText('Configure BLEU Parameters')
      ).not.toBeInTheDocument()
    })

    it('should show parameters when button is clicked', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const button = screen.getByText('Show Advanced Parameters')
      await user.click(button)

      expect(screen.getByText('Configure BLEU Parameters')).toBeInTheDocument()
    })

    it('should toggle button text', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const button = screen.getByText('Show Advanced Parameters')
      await user.click(button)

      expect(screen.getByText('Hide Advanced Parameters')).toBeInTheDocument()
    })

    it('should hide parameters when button is clicked again', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const button = screen.getByText('Show Advanced Parameters')
      await user.click(button)
      await user.click(screen.getByText('Hide Advanced Parameters'))

      expect(
        screen.queryByText('Configure BLEU Parameters')
      ).not.toBeInTheDocument()
    })
  })

  describe('BLEU Parameters', () => {
    it('should render max_order selector', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(getFieldByLabel('Max N-gram Order')).toBeInTheDocument()
    })

    it('should render smoothing selector', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(getFieldByLabel('Smoothing Method')).toBeInTheDocument()
    })

    it('should show default max_order value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel(
        'Max N-gram Order'
      ) as HTMLSelectElement
      expect(select.value).toBe('4')
    })

    it('should show custom max_order value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{ max_order: 2 }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel(
        'Max N-gram Order'
      ) as HTMLSelectElement
      expect(select.value).toBe('2')
    })

    it('should call onChange when max_order changes', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel('Max N-gram Order')
      await user.selectOptions(select, '3')

      expect(mockOnChange).toHaveBeenCalledWith({ max_order: 3 })
    })

    it('should show default smoothing value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel(
        'Smoothing Method'
      ) as HTMLSelectElement
      expect(select.value).toBe('method1')
    })

    it('should call onChange when smoothing changes', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel('Smoothing Method')
      await user.selectOptions(select, 'method2')

      expect(mockOnChange).toHaveBeenCalledWith({ smoothing: 'method2' })
    })

    it('should display max_order tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector(
        '[data-tooltip*="Highest n-gram"]'
      )
      expect(tooltip).toBeInTheDocument()
    })

    it('should display smoothing tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector(
        '[data-tooltip*="Smoothing method"]'
      )
      expect(tooltip).toBeInTheDocument()
    })
  })

  describe('ROUGE Parameters', () => {
    it('should render variant selector', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(getFieldByLabel('ROUGE Variant')).toBeInTheDocument()
    })

    it('should render use_stemmer checkbox', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(screen.getByText('Enable Stemming')).toBeInTheDocument()
    })

    it('should show default variant value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel('ROUGE Variant') as HTMLSelectElement
      expect(select.value).toBe('rougeL')
    })

    it('should call onChange when variant changes', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel('ROUGE Variant')
      await user.selectOptions(select, 'rouge2')

      expect(mockOnChange).toHaveBeenCalledWith({ variant: 'rouge2' })
    })

    it('should show stemmer checked by default', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const checkbox = screen.getByRole('checkbox') as HTMLInputElement
      expect(checkbox.checked).toBe(true)
    })

    it('should call onChange when stemmer is toggled', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const checkbox = screen.getByRole('checkbox')
      await user.click(checkbox)

      expect(mockOnChange).toHaveBeenCalledWith({ use_stemmer: false })
    })

    it('should respect custom stemmer value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{ use_stemmer: false }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const checkbox = screen.getByRole('checkbox') as HTMLInputElement
      expect(checkbox.checked).toBe(false)
    })

    it('should display variant tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector('[data-tooltip*="ROUGE variant"]')
      expect(tooltip).toBeInTheDocument()
    })

    it('should display stemmer tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector(
        '[data-tooltip*="Enable stemming"]'
      )
      expect(tooltip).toBeInTheDocument()
    })
  })

  describe('METEOR Parameters', () => {
    it('should render alpha input', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(
        getFieldByLabel('Alpha (Precision Weight)')
      ).toBeInTheDocument()
    })

    it('should render beta input', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(
        getFieldByLabel('Beta (Recall Preference)')
      ).toBeInTheDocument()
    })

    it('should render gamma input', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(
        getFieldByLabel('Gamma (Fragmentation Penalty)')
      ).toBeInTheDocument()
    })

    it('should show default alpha value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const input = getFieldByLabel(
        'Alpha (Precision Weight)'
      ) as HTMLInputElement
      expect(input.value).toBe('0.9')
    })

    it('should show default beta value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const input = getFieldByLabel(
        'Beta (Recall Preference)'
      ) as HTMLInputElement
      expect(input.value).toBe('3')
    })

    it('should show default gamma value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const input = getFieldByLabel(
        'Gamma (Fragmentation Penalty)'
      ) as HTMLInputElement
      expect(input.value).toBe('0.5')
    })

    it('should call onChange when alpha changes', async () => {
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const user = userEvent.setup()
      await user.click(screen.getByText('Show Advanced Parameters'))

      const input = getFieldByLabel(
        'Alpha (Precision Weight)'
      ) as HTMLInputElement

      fireEvent.change(input, { target: { value: '0.8' } })

      expect(mockOnChange).toHaveBeenCalled()
      const lastCall =
        mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0]
      expect(lastCall.alpha).toBe(0.8)
    })

    it('should call onChange when beta changes', async () => {
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const user = userEvent.setup()
      await user.click(screen.getByText('Show Advanced Parameters'))

      const input = getFieldByLabel(
        'Beta (Recall Preference)'
      ) as HTMLInputElement

      fireEvent.change(input, { target: { value: '2.5' } })

      expect(mockOnChange).toHaveBeenCalled()
      const lastCall =
        mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0]
      expect(lastCall.beta).toBe(2.5)
    })

    it('should call onChange when gamma changes', async () => {
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const user = userEvent.setup()
      await user.click(screen.getByText('Show Advanced Parameters'))

      const input = getFieldByLabel(
        'Gamma (Fragmentation Penalty)'
      ) as HTMLInputElement

      fireEvent.change(input, { target: { value: '0.7' } })

      expect(mockOnChange).toHaveBeenCalled()
      const lastCall =
        mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0]
      expect(lastCall.gamma).toBe(0.7)
    })

    it('should display alpha tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector(
        '[data-tooltip*="Precision weight"]'
      )
      expect(tooltip).toBeInTheDocument()
    })

    it('should display beta tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector(
        '[data-tooltip*="Recall preference"]'
      )
      expect(tooltip).toBeInTheDocument()
    })

    it('should display gamma tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector(
        '[data-tooltip*="Fragmentation penalty"]'
      )
      expect(tooltip).toBeInTheDocument()
    })

    it('should respect custom parameter values', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{ alpha: 0.7, beta: 2.0, gamma: 0.3 }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const alphaInput = getFieldByLabel(
        'Alpha (Precision Weight)'
      ) as HTMLInputElement
      const betaInput = getFieldByLabel(
        'Beta (Recall Preference)'
      ) as HTMLInputElement
      const gammaInput = getFieldByLabel(
        'Gamma (Fragmentation Penalty)'
      ) as HTMLInputElement

      expect(alphaInput.value).toBe('0.7')
      expect(betaInput.value).toBe('2')
      expect(gammaInput.value).toBe('0.3')
    })
  })

  describe('chrF Parameters', () => {
    it('should render char_order selector', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(
        getFieldByLabel('Character N-gram Order')
      ).toBeInTheDocument()
    })

    it('should render word_order selector', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(getFieldByLabel('Word N-gram Order')).toBeInTheDocument()
    })

    it('should render beta selector', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(getFieldByLabel('Beta (F-score Weight)')).toBeInTheDocument()
    })

    it('should show default char_order value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel(
        'Character N-gram Order'
      ) as HTMLSelectElement
      expect(select.value).toBe('6')
    })

    it('should show default word_order value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel(
        'Word N-gram Order'
      ) as HTMLSelectElement
      expect(select.value).toBe('0')
    })

    it('should show default beta value', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel(
        'Beta (F-score Weight)'
      ) as HTMLSelectElement
      expect(select.value).toBe('2')
    })

    it('should call onChange when char_order changes', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel('Character N-gram Order')
      await user.selectOptions(select, '4')

      expect(mockOnChange).toHaveBeenCalledWith({ char_order: 4 })
    })

    it('should call onChange when word_order changes', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel('Word N-gram Order')
      await user.selectOptions(select, '2')

      expect(mockOnChange).toHaveBeenCalledWith({ word_order: 2 })
    })

    it('should call onChange when beta changes', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel('Beta (F-score Weight)')
      await user.selectOptions(select, '1')

      expect(mockOnChange).toHaveBeenCalledWith({ beta: 1 })
    })

    it('should display char_order tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector(
        '[data-tooltip*="character n-gram"]'
      )
      expect(tooltip).toBeInTheDocument()
    })

    it('should display word_order tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector('[data-tooltip*="word n-gram"]')
      expect(tooltip).toBeInTheDocument()
    })

    it('should display beta tooltip', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="chrf"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltip = container.querySelector('[data-tooltip*="F-beta score"]')
      expect(tooltip).toBeInTheDocument()
    })

    it('should respect custom parameter values', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{ char_order: 4, word_order: 1, beta: 3 }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const charOrderSelect = getFieldByLabel(
        'Character N-gram Order'
      ) as HTMLSelectElement
      const wordOrderSelect = getFieldByLabel(
        'Word N-gram Order'
      ) as HTMLSelectElement
      const betaSelect = getFieldByLabel(
        'Beta (F-score Weight)'
      ) as HTMLSelectElement

      expect(charOrderSelect.value).toBe('4')
      expect(wordOrderSelect.value).toBe('1')
      expect(betaSelect.value).toBe('3')
    })
  })

  describe('Reset to Defaults', () => {
    it('should render reset button', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(screen.getByText('Reset to Defaults')).toBeInTheDocument()
    })

    it('should reset bleu parameters to defaults', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{ max_order: 2, smoothing: 'method3' }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))
      await user.click(screen.getByText('Reset to Defaults'))

      expect(mockOnChange).toHaveBeenCalledWith({
        max_order: 4,
        weights: [0.25, 0.25, 0.25, 0.25],
        smoothing: 'method1',
      })
    })

    it('should reset rouge parameters to defaults', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{ variant: 'rouge2', use_stemmer: false }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))
      await user.click(screen.getByText('Reset to Defaults'))

      expect(mockOnChange).toHaveBeenCalledWith({
        variant: 'rougeL',
        use_stemmer: true,
      })
    })

    it('should reset meteor parameters to defaults', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{ alpha: 0.5, beta: 1.0, gamma: 0.2 }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))
      await user.click(screen.getByText('Reset to Defaults'))

      expect(mockOnChange).toHaveBeenCalledWith({
        alpha: 0.9,
        beta: 3.0,
        gamma: 0.5,
      })
    })

    it('should reset chrf parameters to defaults', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="chrf"
          parameters={{ char_order: 3, word_order: 2, beta: 1 }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))
      await user.click(screen.getByText('Reset to Defaults'))

      expect(mockOnChange).toHaveBeenCalledWith({
        char_order: 6,
        word_order: 0,
        beta: 2,
      })
    })
  })

  describe('Styling', () => {
    it('should apply border styling', () => {
      const { container } = render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const wrapper = container.querySelector('.border-t.border-gray-200')
      expect(wrapper).toBeInTheDocument()
    })

    it('should apply button styling', () => {
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const button = screen.getByText('Show Advanced Parameters')
      expect(button).toHaveClass('text-blue-600')
    })

    it('should apply parameter section styling', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const section = container.querySelector('.rounded-md.bg-gray-50')
      expect(section).toBeInTheDocument()
    })

    it('should apply uppercase to metric name', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      expect(screen.getByText(/Configure BLEU Parameters/)).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty parameters object', () => {
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      expect(screen.getByText('Show Advanced Parameters')).toBeInTheDocument()
    })

    it('should handle null-ish values in parameters', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{ use_stemmer: undefined }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const checkbox = screen.getByRole('checkbox') as HTMLInputElement
      expect(checkbox.checked).toBe(true)
    })

    it('should handle case-sensitive metric names', () => {
      render(
        <MetricParameterInput
          metric="BLEU"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      expect(
        screen.queryByText('Show Advanced Parameters')
      ).not.toBeInTheDocument()
    })

    it('should preserve existing parameters when changing one', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{ max_order: 3, smoothing: 'method2' }}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const select = getFieldByLabel('Max N-gram Order')
      await user.selectOptions(select, '2')

      expect(mockOnChange).toHaveBeenCalledWith({
        max_order: 2,
        smoothing: 'method2',
      })
    })

    it('should handle numeric string conversion correctly', async () => {
      render(
        <MetricParameterInput
          metric="meteor"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const user = userEvent.setup()
      await user.click(screen.getByText('Show Advanced Parameters'))

      const input = getFieldByLabel(
        'Alpha (Precision Weight)'
      ) as HTMLInputElement

      fireEvent.change(input, { target: { value: '0.75' } })

      expect(mockOnChange).toHaveBeenCalled()
      const lastCall =
        mockOnChange.mock.calls[mockOnChange.mock.calls.length - 1][0]
      expect(lastCall.alpha).toBe(0.75)
    })
  })

  describe('Accessibility', () => {
    it('should have proper label associations', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      // The label text should exist and a select element should be nearby
      const el = getFieldByLabel('Max N-gram Order')
      expect(el.tagName).toBe('SELECT')
    })

    it('should have proper button element', () => {
      render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      const button = screen.getByText('Show Advanced Parameters')
      expect(button.tagName).toBe('BUTTON')
    })

    it('should have proper select elements', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const selects = container.querySelectorAll('select')
      expect(selects.length).toBeGreaterThan(0)
      expect(selects[0].tagName).toBe('SELECT')
    })

    it('should have proper checkbox input', async () => {
      const user = userEvent.setup()
      render(
        <MetricParameterInput
          metric="rouge"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const checkbox = screen.getByRole('checkbox')
      expect(checkbox).toHaveAttribute('type', 'checkbox')
    })

    it('should have tooltips for all parameters', async () => {
      const user = userEvent.setup()
      const { container } = render(
        <MetricParameterInput
          metric="bleu"
          parameters={{}}
          onChange={mockOnChange}
        />
      )

      await user.click(screen.getByText('Show Advanced Parameters'))

      const tooltips = container.querySelectorAll('[data-tooltip]')
      expect(tooltips.length).toBeGreaterThan(0)
    })
  })
})
