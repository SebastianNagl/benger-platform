/**
 * @jest-environment jsdom
 *
 * Comprehensive tests for Architecture page
 * Tests rendering, sections, navigation, markdown rendering, and content display
 */

import ArchitecturePage from '@/app/architecture/page'
import { render, screen } from '@testing-library/react'

// Mock dependencies
jest.mock('@/components/shared', () => ({
  HeroPattern: () => <div data-testid="hero-pattern">Hero Pattern</div>,
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => {
      const translations: Record<string, any> = {
        'architecture.title': 'System Architecture',
        'architecture.subtitle':
          'A comprehensive overview of **BenGER** architecture',
        'architecture.sections.overview': 'Overview',
        'architecture.sections.frontend': 'Frontend',
        'architecture.sections.apiGateway': 'API Gateway',
        'architecture.sections.celeryWorker': 'Celery Worker',
        'architecture.sections.nativeAnnotation': 'Native Annotation System',
        'architecture.sections.featureFlags': 'Feature Flags',
        'architecture.sections.multiOrgSystem': 'Multi-Organization System',
        'architecture.sections.notificationSystem': 'Notification System',
        'architecture.sections.databases': 'Databases',
        'architecture.sections.deployment': 'Deployment',
        'legal.architecture.content.frontendDesc':
          'Frontend built with **Next.js 15**',
        'architecture.content.frontend.keyFeaturesTitle': 'Key Features',
        'architecture.content.frontend.keyFeatures': [
          'Server-side rendering',
          'Real-time updates',
          'Responsive design',
        ],
        'legal.architecture.content.apiGatewayDesc':
          'API Gateway using **FastAPI**',
        'architecture.content.apiGateway.coreComponentsTitle':
          'Core Components',
        'architecture.content.apiGateway.coreComponents': [
          'REST API endpoints',
          'Authentication middleware',
          'Request validation',
        ],
        'legal.architecture.content.celeryWorkerDesc':
          'Async task processing with **Celery**',
        'architecture.content.celeryWorker.workerTasksTitle': 'Worker Tasks',
        'architecture.content.celeryWorker.workerTasks': [
          'Data import',
          'Email sending',
          'Report generation',
        ],
        'legal.architecture.content.nativeAnnotationDesc':
          'Native annotation system for BenGER',
        'architecture.content.nativeAnnotation.title':
          'Native Annotation System',
        'architecture.content.nativeAnnotation.coreFeaturesTitle':
          'Core Features',
        'architecture.content.nativeAnnotation.coreFeatures': [
          'Real-time collaboration',
          'Multiple annotation types',
          'Quality control',
        ],
        'architecture.content.nativeAnnotation.performanceTitle': 'Performance',
        'architecture.content.nativeAnnotation.performanceImprovements': [
          'Optimized rendering',
          'Efficient caching',
        ],
        'legal.architecture.content.featureFlagsDesc': 'Feature flag system',
        'architecture.content.featureFlags.title': 'Feature Flags',
        'architecture.content.featureFlags.keyCapabilitiesTitle':
          'Key Capabilities',
        'architecture.content.featureFlags.keyCapabilities': [
          'Enable/disable features',
          'A/B testing support',
        ],
        'architecture.content.featureFlags.usagePatternsTitle':
          'Usage Patterns',
        'architecture.content.featureFlags.usagePatterns': [
          'Gradual rollout',
          'Emergency rollback',
        ],
        'legal.architecture.content.multiOrgDesc':
          'Support for **multiple organizations**',
        'architecture.content.multiOrg.coreFunctionsTitle': 'Core Functions',
        'architecture.content.multiOrg.coreFunctions': [
          'Organization management',
          'User assignment',
          'Access control',
        ],
        'legal.architecture.content.notificationDesc':
          'Real-time **notification system**',
        'architecture.content.notifications.notificationTypesTitle':
          'Notification Types',
        'architecture.content.notifications.notificationTypes': [
          'Email notifications',
          'In-app alerts',
          'Push notifications',
        ],
        'legal.architecture.content.databasesDesc':
          'Database architecture with **PostgreSQL** and **Redis**',
        'architecture.content.databases.postgresqlTitle': 'PostgreSQL',
        'architecture.content.databases.postgresqlDesc': 'Primary database',
        'architecture.content.databases.postgresqlFeatures': [
          'ACID compliance',
          'Full-text search',
          'JSON support',
        ],
        'architecture.content.databases.redisTitle': 'Redis',
        'architecture.content.databases.redisDesc': 'Cache and queue',
        'architecture.content.databases.redisFeatures': [
          'In-memory caching',
          'Pub/sub messaging',
          'Task queuing',
        ],
        'legal.architecture.content.deploymentDesc':
          'Deployment with **Docker** and **Kubernetes**',
        'architecture.content.deployment.developmentTitle': 'Development',
        'architecture.content.deployment.developmentDesc':
          'Local development setup',
        'architecture.content.deployment.developmentFeatures': [
          'Docker Compose',
          'Hot reload',
          'Debug mode',
        ],
        'architecture.content.deployment.productionTitle': 'Production',
        'architecture.content.deployment.productionDesc':
          'Production deployment',
        'architecture.content.deployment.productionFeatures': [
          'Kubernetes cluster',
          'Auto-scaling',
          'Load balancing',
        ],
      }
      return translations[key] || key
    },
    currentLanguage: 'en',
  }),
}))

describe('Architecture Page', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  describe('Page Structure', () => {
    it('renders without crashing', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('System Architecture')).toBeInTheDocument()
    })

    it('renders hero pattern component', () => {
      render(<ArchitecturePage />)
      expect(screen.getByTestId('hero-pattern')).toBeInTheDocument()
    })

    it('renders main container with correct styling', () => {
      const { container } = render(<ArchitecturePage />)
      const mainContainer = container.querySelector(
        '.container.mx-auto.max-w-5xl'
      )
      expect(mainContainer).toBeInTheDocument()
    })

    it('renders page title correctly', () => {
      render(<ArchitecturePage />)
      const title = screen.getByText('System Architecture')
      expect(title).toBeInTheDocument()
      expect(title.tagName).toBe('H1')
    })

    it('renders page subtitle with markdown', () => {
      render(<ArchitecturePage />)
      const subtitle = screen.getByText(/A comprehensive overview/)
      expect(subtitle).toBeInTheDocument()
    })
  })

  describe('Markdown Rendering', () => {
    it('converts markdown bold syntax to HTML strong tags', () => {
      render(<ArchitecturePage />)
      const subtitle = screen.getByText(/A comprehensive overview/)
      expect(subtitle.innerHTML).toContain('<strong>BenGER</strong>')
    })

    it('renders multiple bold elements in same text', () => {
      render(<ArchitecturePage />)
      const elements = screen.getAllByText(/Next.js 15/i)
      expect(elements.length).toBeGreaterThan(0)
    })

    it('preserves non-markdown text correctly', () => {
      render(<ArchitecturePage />)
      const subtitle = screen.getByText(/A comprehensive overview/)
      expect(subtitle.textContent).toContain('A comprehensive overview')
    })
  })

  describe('Overview Section', () => {
    it('renders overview section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#overview')
      expect(section).toBeInTheDocument()
    })

    it('renders overview section heading', () => {
      render(<ArchitecturePage />)
      const heading = screen.getByText('Overview')
      expect(heading).toBeInTheDocument()
      expect(heading.tagName).toBe('H2')
    })

    it('renders architecture diagram in pre element', () => {
      const { container } = render(<ArchitecturePage />)
      const preElement = container.querySelector('pre')
      expect(preElement).toBeInTheDocument()
      expect(preElement?.textContent).toContain('Frontend')
      expect(preElement?.textContent).toContain('API Gateway')
      expect(preElement?.textContent).toContain('Workers')
    })

    it('displays all main components in diagram', () => {
      const { container } = render(<ArchitecturePage />)
      const preElement = container.querySelector('pre')
      expect(preElement?.textContent).toContain('Next.js 15')
      expect(preElement?.textContent).toContain('FastAPI')
      expect(preElement?.textContent).toContain('Celery')
      expect(preElement?.textContent).toContain('Traefik')
      expect(preElement?.textContent).toContain('PostgreSQL')
      expect(preElement?.textContent).toContain('Redis')
    })
  })

  describe('Frontend Section', () => {
    it('renders frontend section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#frontend')
      expect(section).toBeInTheDocument()
    })

    it('renders frontend section heading', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Frontend')).toBeInTheDocument()
    })

    it('renders frontend description with markdown', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText(/Frontend built with/)).toBeInTheDocument()
    })

    it('renders key features subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Key Features')).toBeInTheDocument()
    })

    it('renders all frontend features as list items', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Server-side rendering')).toBeInTheDocument()
      expect(screen.getByText('Real-time updates')).toBeInTheDocument()
      expect(screen.getByText('Responsive design')).toBeInTheDocument()
    })
  })

  describe('API Gateway Section', () => {
    it('renders API gateway section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#api-gateway')
      expect(section).toBeInTheDocument()
    })

    it('renders API gateway section heading', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('API Gateway')).toBeInTheDocument()
    })

    it('renders API gateway description', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText(/API Gateway using/)).toBeInTheDocument()
    })

    it('renders core components subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Core Components')).toBeInTheDocument()
    })

    it('renders all API components as list items', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('REST API endpoints')).toBeInTheDocument()
      expect(screen.getByText('Authentication middleware')).toBeInTheDocument()
      expect(screen.getByText('Request validation')).toBeInTheDocument()
    })
  })

  describe('Celery Worker Section', () => {
    it('renders celery worker section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#celery-worker')
      expect(section).toBeInTheDocument()
    })

    it('renders celery worker heading', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Celery Worker')).toBeInTheDocument()
    })

    it('renders worker description', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText(/Async task processing/)).toBeInTheDocument()
    })

    it('renders worker tasks subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Worker Tasks')).toBeInTheDocument()
    })

    it('renders all worker tasks as list items', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Data import')).toBeInTheDocument()
      expect(screen.getByText('Email sending')).toBeInTheDocument()
      expect(screen.getByText('Report generation')).toBeInTheDocument()
    })
  })

  describe('Native Annotation System Section', () => {
    it('renders native annotation section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#native-annotation-system')
      expect(section).toBeInTheDocument()
    })

    it('renders native annotation heading', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Native Annotation System')).toBeInTheDocument()
    })

    it('renders annotation description', () => {
      render(<ArchitecturePage />)
      expect(
        screen.getByText('Native annotation system for BenGER')
      ).toBeInTheDocument()
    })

    it('renders core features subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getAllByText('Core Features')[0]).toBeInTheDocument()
    })

    it('renders all annotation features', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Real-time collaboration')).toBeInTheDocument()
      expect(screen.getByText('Multiple annotation types')).toBeInTheDocument()
      expect(screen.getByText('Quality control')).toBeInTheDocument()
    })

    it('renders performance subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Performance')).toBeInTheDocument()
    })

    it('renders performance improvements', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Optimized rendering')).toBeInTheDocument()
      expect(screen.getByText('Efficient caching')).toBeInTheDocument()
    })
  })

  describe('Feature Flags Section', () => {
    it('renders feature flags section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#feature-flags')
      expect(section).toBeInTheDocument()
    })

    it('renders feature flags heading', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Feature Flags')).toBeInTheDocument()
    })

    it('renders feature flags description', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Feature flag system')).toBeInTheDocument()
    })

    it('renders key capabilities subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Key Capabilities')).toBeInTheDocument()
    })

    it('renders all feature flag capabilities', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Enable/disable features')).toBeInTheDocument()
      expect(screen.getByText('A/B testing support')).toBeInTheDocument()
    })

    it('renders usage patterns subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Usage Patterns')).toBeInTheDocument()
    })

    it('renders usage patterns', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Gradual rollout')).toBeInTheDocument()
      expect(screen.getByText('Emergency rollback')).toBeInTheDocument()
    })
  })

  describe('Multi-Organization System Section', () => {
    it('renders multi-org section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#multi-organisation-system')
      expect(section).toBeInTheDocument()
    })

    it('renders multi-org heading', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Multi-Organization System')).toBeInTheDocument()
    })

    it('renders multi-org description', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText(/Support for/)).toBeInTheDocument()
    })

    it('renders core functions subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Core Functions')).toBeInTheDocument()
    })

    it('renders all multi-org functions', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Organization management')).toBeInTheDocument()
      expect(screen.getByText('User assignment')).toBeInTheDocument()
      expect(screen.getByText('Access control')).toBeInTheDocument()
    })
  })

  describe('Notification System Section', () => {
    it('renders notification section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#notification-system')
      expect(section).toBeInTheDocument()
    })

    it('renders notification heading', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Notification System')).toBeInTheDocument()
    })

    it('renders notification description', () => {
      render(<ArchitecturePage />)
      const elements = screen.getAllByText(/Real-time/)
      expect(elements.length).toBeGreaterThan(0)
    })

    it('renders notification types subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Notification Types')).toBeInTheDocument()
    })

    it('renders all notification types', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Email notifications')).toBeInTheDocument()
      expect(screen.getByText('In-app alerts')).toBeInTheDocument()
      expect(screen.getByText('Push notifications')).toBeInTheDocument()
    })
  })

  describe('Databases Section', () => {
    it('renders databases section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#databases')
      expect(section).toBeInTheDocument()
    })

    it('renders databases heading', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Databases')).toBeInTheDocument()
    })

    it('renders databases description', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText(/Database architecture/)).toBeInTheDocument()
    })

    it('renders PostgreSQL subsection', () => {
      render(<ArchitecturePage />)
      const postgresqlElements = screen.getAllByText('PostgreSQL')
      expect(postgresqlElements.length).toBeGreaterThan(0)
      expect(screen.getByText('Primary database')).toBeInTheDocument()
    })

    it('renders all PostgreSQL features', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('ACID compliance')).toBeInTheDocument()
      expect(screen.getByText('Full-text search')).toBeInTheDocument()
      expect(screen.getByText('JSON support')).toBeInTheDocument()
    })

    it('renders Redis subsection', () => {
      render(<ArchitecturePage />)
      const redisElements = screen.getAllByText('Redis')
      expect(redisElements.length).toBeGreaterThan(0)
      expect(screen.getByText('Cache and queue')).toBeInTheDocument()
    })

    it('renders all Redis features', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('In-memory caching')).toBeInTheDocument()
      expect(screen.getByText('Pub/sub messaging')).toBeInTheDocument()
      expect(screen.getByText('Task queuing')).toBeInTheDocument()
    })
  })

  describe('Deployment Section', () => {
    it('renders deployment section with correct id', () => {
      const { container } = render(<ArchitecturePage />)
      const section = container.querySelector('#deployment')
      expect(section).toBeInTheDocument()
    })

    it('renders deployment heading', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Deployment')).toBeInTheDocument()
    })

    it('renders deployment description', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText(/Deployment with/)).toBeInTheDocument()
    })

    it('renders development subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Development')).toBeInTheDocument()
      expect(screen.getByText('Local development setup')).toBeInTheDocument()
    })

    it('renders all development features', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Docker Compose')).toBeInTheDocument()
      expect(screen.getByText('Hot reload')).toBeInTheDocument()
      expect(screen.getByText('Debug mode')).toBeInTheDocument()
    })

    it('renders production subsection', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Production')).toBeInTheDocument()
      expect(screen.getByText('Production deployment')).toBeInTheDocument()
    })

    it('renders all production features', () => {
      render(<ArchitecturePage />)
      expect(screen.getByText('Kubernetes cluster')).toBeInTheDocument()
      expect(screen.getByText('Auto-scaling')).toBeInTheDocument()
      expect(screen.getByText('Load balancing')).toBeInTheDocument()
    })
  })

  describe('All Sections Rendering', () => {
    it('renders all 10 main sections', () => {
      const { container } = render(<ArchitecturePage />)

      expect(container.querySelector('#overview')).toBeInTheDocument()
      expect(container.querySelector('#frontend')).toBeInTheDocument()
      expect(container.querySelector('#api-gateway')).toBeInTheDocument()
      expect(container.querySelector('#celery-worker')).toBeInTheDocument()
      expect(
        container.querySelector('#native-annotation-system')
      ).toBeInTheDocument()
      expect(container.querySelector('#feature-flags')).toBeInTheDocument()
      expect(
        container.querySelector('#multi-organisation-system')
      ).toBeInTheDocument()
      expect(
        container.querySelector('#notification-system')
      ).toBeInTheDocument()
      expect(container.querySelector('#databases')).toBeInTheDocument()
      expect(container.querySelector('#deployment')).toBeInTheDocument()
    })

    it('renders sections in correct order', () => {
      const { container } = render(<ArchitecturePage />)
      const sections = container.querySelectorAll('section')

      expect(sections[0]).toHaveAttribute('id', 'overview')
      expect(sections[1]).toHaveAttribute('id', 'frontend')
      expect(sections[2]).toHaveAttribute('id', 'api-gateway')
      expect(sections[3]).toHaveAttribute('id', 'celery-worker')
    })
  })

  describe('Styling and Layout', () => {
    it('applies correct container styling', () => {
      const { container } = render(<ArchitecturePage />)
      const mainDiv = container.querySelector(
        '.container.mx-auto.max-w-5xl.px-4.pb-10.pt-16'
      )
      expect(mainDiv).toBeInTheDocument()
    })

    it('applies correct heading styles', () => {
      render(<ArchitecturePage />)
      const h1 = screen.getByText('System Architecture')
      expect(h1).toHaveClass('text-3xl', 'font-bold')
    })

    it('applies correct section spacing', () => {
      const { container } = render(<ArchitecturePage />)
      const sectionsContainer = container.querySelector('.space-y-12')
      expect(sectionsContainer).toBeInTheDocument()
    })

    it('applies dark mode classes', () => {
      render(<ArchitecturePage />)
      const title = screen.getByText('System Architecture')
      expect(title).toHaveClass('dark:text-white')
    })
  })

  describe('Accessibility', () => {
    it('uses semantic HTML section elements', () => {
      const { container } = render(<ArchitecturePage />)
      const sections = container.querySelectorAll('section')
      expect(sections.length).toBeGreaterThan(0)
    })

    it('has proper heading hierarchy', () => {
      const { container } = render(<ArchitecturePage />)
      const h1 = container.querySelector('h1')
      const h2s = container.querySelectorAll('h2')
      const h3s = container.querySelectorAll('h3')

      expect(h1).toBeInTheDocument()
      expect(h2s.length).toBeGreaterThan(0)
      expect(h3s.length).toBeGreaterThan(0)
    })

    it('provides section IDs for navigation', () => {
      const { container } = render(<ArchitecturePage />)
      const sectionsWithIds = container.querySelectorAll('section[id]')
      expect(sectionsWithIds.length).toBe(10)
    })
  })
})
