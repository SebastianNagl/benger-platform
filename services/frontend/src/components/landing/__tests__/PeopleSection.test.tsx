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
      'landing.people.title': 'Group & Network',
      'landing.people.subtitle': 'Meet the team behind BenGER.',
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
      expect(screen.getByText('Group & Network')).toBeInTheDocument()
      expect(
        screen.getByText('Meet the team behind BenGER.')
      ).toBeInTheDocument()
    })

    it('renders section with min-h-screen', () => {
      const { container } = render(<PeopleSection />)
      const section = container.querySelector('#people')
      expect(section).toHaveClass('min-h-screen')
    })

    it('renders one block: no team/acknowledgement sub-headers, only the network label', () => {
      render(<PeopleSection />)
      expect(screen.queryByText('Team — Platform')).not.toBeInTheDocument()
      expect(screen.queryByText('Acknowledgements')).not.toBeInTheDocument()
      expect(screen.getByText('Network & Partners')).toBeInTheDocument()
    })
  })

  describe('team cards', () => {
    it('renders correct number of cards', () => {
      render(<PeopleSection />)
      const cards = screen.getAllByTestId('card')
      // People are merged into one list and de-duplicated by name:
      // Sebastian (platform + dataset core) once, Matthias, Team Member,
      // Senior Author, Acknowledged Person = 5, plus 2 network = 7.
      expect(cards).toHaveLength(7)
    })

    it('lists a person appearing in several source lists only once', () => {
      render(<PeopleSection />)
      expect(screen.getAllByText('Sebastian Nagl')).toHaveLength(1)
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
      expect(h2).toHaveTextContent('Group & Network')

      // One block under the h2: every person name is an h3 (5 unique people
      // in the mocks) plus the network label — no skipped heading level.
      const h3s = screen.getAllByRole('heading', { level: 3 })
      expect(h3s).toHaveLength(6)
      expect(screen.getByRole('heading', { level: 3, name: 'Sebastian Nagl' })).toBeInTheDocument()
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
