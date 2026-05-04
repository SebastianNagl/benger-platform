import { render, screen } from '@testing-library/react'
import { PeopleSection } from '../PeopleSection'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: jest.fn(),
}))

jest.mock('next/image', () => {
  function MockImage({ alt, ...props }: any) {
    return <img alt={alt} {...props} />
  }
  return MockImage
})

jest.mock('@/components/shared/Card', () => ({
  Card: ({ children, className }: any) => (
    <div data-testid="card" className={className}>
      {children}
    </div>
  ),
}))

const mockUseI18n = require('@/contexts/I18nContext').useI18n

describe('PeopleSection', () => {
  const mockTeamPlatform = [
    {
      name: 'Sebastian Nagl',
      role: 'Project Lead',
      institution: 'TUM',
      url: 'https://legalplusplus.net',
    },
    {
      name: 'Matthias Grabmair',
      role: 'Project Supervisor',
      institution: 'TUM',
      url: '',
    },
  ]

  const mockTeamDatasetCore = [
    {
      name: 'Sebastian Nagl',
      role: 'Project Lead',
      institution: 'TUM',
      url: 'https://legalplusplus.net',
    },
  ]

  const mockTeamDatasetContribution = [
    {
      name: 'Team Member',
      role: 'Research Associate',
      institution: 'TUM',
      url: '',
    },
  ]

  const mockTeamDatasetSenior = [
    {
      name: 'Senior Author',
      role: 'Criminal Law',
      institution: 'University',
      url: '',
    },
  ]

  const mockAcknowledgements = [
    {
      name: 'Acknowledged Person',
      role: 'Coordination',
      institution: 'TUM',
      url: '',
    },
  ]

  const mockNetwork = [
    {
      name: 'Technical University of Munich',
      description: 'Chair of Legal Technology',
      url: 'https://www.tum.de',
      logo: '/tum-logo-official.svg',
    },
    {
      name: 'LegalTechColab',
      description: 'Collaborative research network.',
      url: 'https://legaltechcolab.com',
    },
  ]

  const mockT = jest.fn((key: string) => {
    const translations: Record<string, any> = {
      'landing.people.title': 'People & Network',
      'landing.people.subtitle': 'Meet the team behind BenGER.',
      'landing.people.teamPlatformTitle': 'Team — Platform',
      'landing.people.teamDatasetTitle': 'Team — Dataset',
      'landing.people.teamDatasetCoreTitle': 'Core Contributor',
      'landing.people.teamDatasetContributionTitle': 'Dataset Contribution',
      'landing.people.teamDatasetSeniorTitle': 'Senior Authors',
      'landing.people.acknowledgementsTitle': 'Acknowledgements',
      'landing.people.networkTitle': 'Network & Partners',
      'landing.people.teamPlatform': mockTeamPlatform,
      'landing.people.teamDatasetCore': mockTeamDatasetCore,
      'landing.people.teamDatasetContribution': mockTeamDatasetContribution,
      'landing.people.teamDatasetSenior': mockTeamDatasetSenior,
      'landing.people.acknowledgements': mockAcknowledgements,
      'landing.people.network': mockNetwork,
    }
    return translations[key] || key
  })

  beforeEach(() => {
    mockUseI18n.mockReturnValue({ t: mockT })
  })

  afterEach(() => {
    jest.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders section with id="people"', () => {
      const { container } = render(<PeopleSection />)
      const section = container.querySelector('#people')
      expect(section).toBeInTheDocument()
    })

    it('renders section title and subtitle', () => {
      render(<PeopleSection />)
      expect(screen.getByText('People & Network')).toBeInTheDocument()
      expect(
        screen.getByText('Meet the team behind BenGER.')
      ).toBeInTheDocument()
    })

    it('renders section with min-h-screen', () => {
      const { container } = render(<PeopleSection />)
      const section = container.querySelector('#people')
      expect(section).toHaveClass('min-h-screen')
    })

    it('renders team, acknowledgements and network sub-headers', () => {
      render(<PeopleSection />)
      expect(screen.getByText('Team — Platform')).toBeInTheDocument()
      expect(screen.getByText('Team — Dataset')).toBeInTheDocument()
      expect(screen.getByText('Core Contributor')).toBeInTheDocument()
      expect(screen.getByText('Dataset Contribution')).toBeInTheDocument()
      expect(screen.getByText('Senior Authors')).toBeInTheDocument()
      expect(screen.getByText('Acknowledgements')).toBeInTheDocument()
      expect(screen.getByText('Network & Partners')).toBeInTheDocument()
    })
  })

  describe('team cards', () => {
    it('renders correct number of cards', () => {
      render(<PeopleSection />)
      const cards = screen.getAllByTestId('card')
      // 2 platform + 1 core + 1 contribution + 1 senior + 1 ack + 2 network = 8
      expect(cards).toHaveLength(8)
    })

    it('renders team member names', () => {
      render(<PeopleSection />)
      // Sebastian appears in platform and dataset core
      expect(screen.getAllByText('Sebastian Nagl').length).toBeGreaterThan(0)
      expect(screen.getByText('Matthias Grabmair')).toBeInTheDocument()
      expect(screen.getByText('Team Member')).toBeInTheDocument()
      expect(screen.getByText('Senior Author')).toBeInTheDocument()
      expect(screen.getByText('Acknowledged Person')).toBeInTheDocument()
    })

    it('renders team member roles', () => {
      render(<PeopleSection />)
      expect(screen.getAllByText('Project Lead').length).toBeGreaterThan(0)
      expect(screen.getByText('Project Supervisor')).toBeInTheDocument()
      expect(screen.getByText('Research Associate')).toBeInTheDocument()
    })

    it('links team members with URLs', () => {
      render(<PeopleSection />)
      const links = screen.getAllByRole('link', { name: 'Sebastian Nagl' })
      links.forEach((link) => {
        expect(link).toHaveAttribute('href', 'https://legalplusplus.net')
        expect(link).toHaveAttribute('target', '_blank')
        expect(link).toHaveAttribute('rel', 'noopener noreferrer')
      })
    })

    it('does not link team members without URLs', () => {
      render(<PeopleSection />)
      const teamMemberText = screen.getByText('Team Member')
      expect(teamMemberText.closest('a')).toBeNull()
    })

    it('renders avatar placeholders', () => {
      const { container } = render(<PeopleSection />)
      const avatars = container.querySelectorAll('.rounded-full')
      expect(avatars.length).toBeGreaterThan(0)
    })
  })

  describe('network cards', () => {
    it('renders network partner names', () => {
      render(<PeopleSection />)
      expect(
        screen.getByText('Technical University of Munich')
      ).toBeInTheDocument()
      expect(screen.getByText('LegalTechColab')).toBeInTheDocument()
    })

    it('renders network partner descriptions', () => {
      render(<PeopleSection />)
      expect(
        screen.getByText('Chair of Legal Technology')
      ).toBeInTheDocument()
      expect(
        screen.getByText('Collaborative research network.')
      ).toBeInTheDocument()
    })

    it('renders logo images when provided', () => {
      render(<PeopleSection />)
      const logo = screen.getByAltText('Technical University of Munich Logo')
      expect(logo).toHaveAttribute('src', '/tum-logo-official.svg')
    })

    it('links network partners with URLs', () => {
      render(<PeopleSection />)
      const tumLink = screen.getByRole('link', {
        name: 'Technical University of Munich',
      })
      expect(tumLink).toHaveAttribute('href', 'https://www.tum.de')
    })
  })

  describe('accessibility', () => {
    it('uses proper heading hierarchy', () => {
      render(<PeopleSection />)
      const h2 = screen.getByRole('heading', { level: 2 })
      expect(h2).toHaveTextContent('People & Network')

      const h3s = screen.getAllByRole('heading', { level: 3 })
      // platform + dataset + acknowledgements + network = 4
      expect(h3s).toHaveLength(4)
    })

    it('opens external links in new tab safely', () => {
      render(<PeopleSection />)
      const externalLinks = screen.getAllByRole('link')
      externalLinks.forEach((link) => {
        expect(link).toHaveAttribute('target', '_blank')
        expect(link).toHaveAttribute('rel', 'noopener noreferrer')
      })
    })
  })

  describe('internationalization', () => {
    it('calls t() for section text', () => {
      render(<PeopleSection />)
      expect(mockT).toHaveBeenCalledWith('landing.people.title')
      expect(mockT).toHaveBeenCalledWith('landing.people.subtitle')
      expect(mockT).toHaveBeenCalledWith('landing.people.teamPlatformTitle')
      expect(mockT).toHaveBeenCalledWith('landing.people.teamDatasetTitle')
      expect(mockT).toHaveBeenCalledWith('landing.people.teamDatasetCoreTitle')
      expect(mockT).toHaveBeenCalledWith(
        'landing.people.teamDatasetContributionTitle'
      )
      expect(mockT).toHaveBeenCalledWith('landing.people.teamDatasetSeniorTitle')
      expect(mockT).toHaveBeenCalledWith('landing.people.acknowledgementsTitle')
      expect(mockT).toHaveBeenCalledWith('landing.people.networkTitle')
      expect(mockT).toHaveBeenCalledWith('landing.people.teamPlatform')
      expect(mockT).toHaveBeenCalledWith('landing.people.teamDatasetCore')
      expect(mockT).toHaveBeenCalledWith('landing.people.teamDatasetContribution')
      expect(mockT).toHaveBeenCalledWith('landing.people.teamDatasetSenior')
      expect(mockT).toHaveBeenCalledWith('landing.people.acknowledgements')
      expect(mockT).toHaveBeenCalledWith('landing.people.network')
    })
  })

  describe('empty state', () => {
    it('handles empty data gracefully', () => {
      const emptyT = jest.fn((key: string) => key)
      mockUseI18n.mockReturnValue({ t: emptyT })

      const { container } = render(<PeopleSection />)
      const cards = container.querySelectorAll('[data-testid="card"]')
      expect(cards).toHaveLength(0)
    })
  })
})
