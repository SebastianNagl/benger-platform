import { fireEvent, render, screen } from '@testing-library/react'
import { InformationSection } from '../InformationSection'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('@/contexts/HydrationContext', () => ({
  useHydration: () => true,
}))

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div data-testid="card" className={className}>
      {children}
    </div>
  ),
}))

const mockUseI18n = require('@/contexts/I18nContext').useI18n

describe('InformationSection', () => {
  const mockTranslations: Record<string, string> = {
    'landing.information.title': 'About BenGER',
    'landing.information.tabs.whatIsIt': 'What is it?',
    'landing.information.tabs.howItWorks': 'How it works',
    'landing.information.tabs.whyNeeded': 'Why this is needed',
    'landing.information.whatIsIt.description': 'BenGER is a research-grade benchmarking platform.',
    'landing.information.whatIsIt.annotation.title': 'Annotation System',
    'landing.information.whatIsIt.annotation.description': 'A complete native annotation system.',
    'landing.information.whatIsIt.generation.title': 'Generation Pipeline',
    'landing.information.whatIsIt.generation.description': 'Run multiple LLMs.',
    'landing.information.whatIsIt.evaluation.title': 'Evaluation Suite',
    'landing.information.whatIsIt.evaluation.description': 'A comprehensive academic evaluation suite.',
    'landing.information.howItWorks.description': 'BenGER guides you through a structured workflow.',
    'landing.information.howItWorks.steps.create.number': '1',
    'landing.information.howItWorks.steps.create.title': 'Create a Project',
    'landing.information.howItWorks.steps.create.description': 'Set up a new project.',
    'landing.information.howItWorks.steps.import.number': '2',
    'landing.information.howItWorks.steps.import.title': 'Import Data',
    'landing.information.howItWorks.steps.import.description': 'Upload your documents.',
    'landing.information.howItWorks.steps.annotate.number': '3',
    'landing.information.howItWorks.steps.annotate.title': 'Annotate',
    'landing.information.howItWorks.steps.annotate.description': 'Expert annotators label your data.',
    'landing.information.howItWorks.steps.generate.number': '4',
    'landing.information.howItWorks.steps.generate.title': 'Generate',
    'landing.information.howItWorks.steps.generate.description': 'Run LLM generations.',
    'landing.information.howItWorks.steps.evaluate.number': '5',
    'landing.information.howItWorks.steps.evaluate.title': 'Evaluate',
    'landing.information.howItWorks.steps.evaluate.description': 'Apply automated metrics.',
    'landing.information.howItWorks.steps.report.number': '6',
    'landing.information.howItWorks.steps.report.title': 'Generate Report',
    'landing.information.howItWorks.steps.report.description': 'Produce publication-ready reports.',
    'landing.information.whyNeeded.description': 'The German legal system presents unique challenges.',
    'landing.information.whyNeeded.gaps.title': 'No German Legal Benchmarks',
    'landing.information.whyNeeded.gaps.description': 'Existing NLP benchmarks focus on English.',
    'landing.information.whyNeeded.rigor.title': 'Scientific Rigor',
    'landing.information.whyNeeded.rigor.description': 'Legal AI demands highest standards.',
    'landing.information.whyNeeded.reproducibility.title': 'Reproducibility',
    'landing.information.whyNeeded.reproducibility.description': 'Academic research requires exact reproducibility.',
  }

  const mockT = jest.fn((key: string) => mockTranslations[key] || key)

  beforeEach(() => {
    mockUseI18n.mockReturnValue({ t: mockT })
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders section with id="information"', () => {
      const { container } = render(<InformationSection />)
      const section = container.querySelector('#information')
      expect(section).toBeInTheDocument()
    })

    it('renders section title', () => {
      render(<InformationSection />)
      expect(screen.getByText('About BenGER')).toBeInTheDocument()
    })

    it('renders section with min-h-screen', () => {
      const { container } = render(<InformationSection />)
      const section = container.querySelector('#information')
      expect(section).toHaveClass('min-h-screen')
    })

    it('renders three tab triggers', () => {
      render(<InformationSection />)
      expect(screen.getByText('What is it?')).toBeInTheDocument()
      expect(screen.getByText('How it works')).toBeInTheDocument()
      expect(screen.getByText('Why this is needed')).toBeInTheDocument()
    })
  })

  describe('tab switching', () => {
    it('shows "What is it?" tab content by default', () => {
      render(<InformationSection />)
      expect(screen.getByText('Annotation System')).toBeInTheDocument()
      expect(screen.getByText('Generation Pipeline')).toBeInTheDocument()
      expect(screen.getByText('Evaluation Suite')).toBeInTheDocument()
    })

    it('shows "How it works" tab content when clicked', () => {
      render(<InformationSection />)
      fireEvent.click(screen.getByText('How it works'))
      expect(screen.getByText('Create a Project')).toBeInTheDocument()
      expect(screen.getByText('Import Data')).toBeInTheDocument()
      expect(screen.getByText('Annotate')).toBeInTheDocument()
    })

    it('shows "Why this is needed" tab content when clicked', () => {
      render(<InformationSection />)
      fireEvent.click(screen.getByText('Why this is needed'))
      expect(screen.getByText('No German Legal Benchmarks')).toBeInTheDocument()
      expect(screen.getByText('Scientific Rigor')).toBeInTheDocument()
      expect(screen.getByText('Reproducibility')).toBeInTheDocument()
    })

    it('hides previous tab content when switching', () => {
      render(<InformationSection />)
      expect(screen.getByText('Annotation System')).toBeInTheDocument()

      fireEvent.click(screen.getByText('How it works'))
      expect(screen.queryByText('Annotation System')).not.toBeInTheDocument()
    })
  })

  describe('how it works tab content', () => {
    it('renders all 6 workflow steps', () => {
      render(<InformationSection />)
      fireEvent.click(screen.getByText('How it works'))

      expect(screen.getByText('1')).toBeInTheDocument()
      expect(screen.getByText('2')).toBeInTheDocument()
      expect(screen.getByText('3')).toBeInTheDocument()
      expect(screen.getByText('4')).toBeInTheDocument()
      expect(screen.getByText('5')).toBeInTheDocument()
      expect(screen.getByText('6')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('uses proper heading hierarchy', () => {
      render(<InformationSection />)
      const heading = screen.getByRole('heading', { level: 2 })
      expect(heading).toHaveTextContent('About BenGER')
    })
  })

  describe('internationalization', () => {
    it('calls t() for section title', () => {
      render(<InformationSection />)
      expect(mockT).toHaveBeenCalledWith('landing.information.title')
    })

    it('calls t() for all tab labels', () => {
      render(<InformationSection />)
      expect(mockT).toHaveBeenCalledWith('landing.information.tabs.whatIsIt')
      expect(mockT).toHaveBeenCalledWith('landing.information.tabs.howItWorks')
      expect(mockT).toHaveBeenCalledWith('landing.information.tabs.whyNeeded')
    })
  })
})
