import { fireEvent, render, screen } from '@testing-library/react'
import { LikertScale } from '../LikertScale'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, string> = {
        'likertScale.stronglyDisagree': 'Strongly disagree',
        'likertScale.stronglyAgree': 'Strongly agree',
      }
      return translations[key] || key
    },
    locale: 'en',
  }),
}))

describe('LikertScale', () => {
  const defaultProps = {
    name: 'test-scale',
    label: 'Rate this item',
    value: undefined as number | undefined,
    onChange: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders the label text', () => {
    render(<LikertScale {...defaultProps} />)
    expect(screen.getByText('Rate this item')).toBeInTheDocument()
  })

  it('renders as a fieldset with legend', () => {
    render(<LikertScale {...defaultProps} />)
    expect(screen.getByRole('group')).toBeInTheDocument()
  })

  it('renders default 7 scale points (1-7)', () => {
    render(<LikertScale {...defaultProps} />)
    for (let i = 1; i <= 7; i++) {
      expect(screen.getByText(String(i))).toBeInTheDocument()
    }
  })

  it('renders custom min/max range', () => {
    render(<LikertScale {...defaultProps} min={1} max={5} />)
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByText(String(i))).toBeInTheDocument()
    }
    expect(screen.queryByText('6')).not.toBeInTheDocument()
  })

  it('shows required asterisk when required', () => {
    render(<LikertScale {...defaultProps} required={true} />)
    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('does not show required asterisk by default', () => {
    render(<LikertScale {...defaultProps} />)
    expect(screen.queryByText('*')).not.toBeInTheDocument()
  })

  it('calls onChange when a point is selected', () => {
    const onChange = jest.fn()
    render(<LikertScale {...defaultProps} onChange={onChange} />)
    fireEvent.click(screen.getByText('4'))
    expect(onChange).toHaveBeenCalledWith(4)
  })

  it('highlights the selected value', () => {
    render(<LikertScale {...defaultProps} value={3} />)
    const selectedLabel = screen.getByText('3').closest('label')
    expect(selectedLabel).toHaveClass('border-emerald-600', 'bg-emerald-600', 'text-white')
  })

  it('does not highlight unselected values', () => {
    render(<LikertScale {...defaultProps} value={3} />)
    const unselectedLabel = screen.getByText('5').closest('label')
    expect(unselectedLabel).toHaveClass('border-zinc-300', 'text-zinc-700')
  })

  it('renders strongly disagree and strongly agree labels', () => {
    render(<LikertScale {...defaultProps} />)
    // Labels appear twice (desktop + mobile)
    const disagreeLabels = screen.getAllByText('Strongly disagree')
    const agreeLabels = screen.getAllByText('Strongly agree')
    expect(disagreeLabels.length).toBe(2)
    expect(agreeLabels.length).toBe(2)
  })

  it('renders radio inputs with correct name', () => {
    render(<LikertScale {...defaultProps} />)
    const radios = screen.getAllByRole('radio')
    radios.forEach((radio) => {
      expect(radio).toHaveAttribute('name', 'test-scale')
    })
  })

  it('renders radio inputs with sr-only class for accessibility', () => {
    render(<LikertScale {...defaultProps} />)
    const radios = screen.getAllByRole('radio')
    radios.forEach((radio) => {
      expect(radio).toHaveClass('sr-only')
    })
  })

  it('marks radio as required when required and no value selected', () => {
    render(<LikertScale {...defaultProps} required={true} />)
    const radios = screen.getAllByRole('radio')
    // All radios should be required when value is undefined
    radios.forEach((radio) => {
      expect(radio).toHaveAttribute('required')
    })
  })

  it('does not mark radio as required when value is selected', () => {
    render(<LikertScale {...defaultProps} required={true} value={3} />)
    const radios = screen.getAllByRole('radio')
    // When a value is selected, required should be false
    radios.forEach((radio) => {
      expect(radio).not.toHaveAttribute('required')
    })
  })

  it('checks the correct radio button', () => {
    render(<LikertScale {...defaultProps} value={5} />)
    const radios = screen.getAllByRole('radio') as HTMLInputElement[]
    const checkedRadio = radios.find((r) => r.checked)
    expect(checkedRadio).toBeTruthy()
    expect(checkedRadio?.value).toBe('5')
  })
})
