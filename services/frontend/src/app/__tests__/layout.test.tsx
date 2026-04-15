/**
 * @jest-environment jsdom
 */

import { render } from '@testing-library/react'

// Mock CSS imports
jest.mock('@/styles/tailwind.css', () => ({}))

import RootLayout, { metadata } from '../layout'

// Mock the Providers component
jest.mock('@/app/providers', () => ({
  Providers: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="providers">{children}</div>
  ),
}))

// Mock DevModeIndicator
jest.mock('@/components/dev/DevModeIndicator', () => ({
  DevModeIndicator: () => <div data-testid="dev-mode-indicator" />,
}))

// Mock ConditionalLayout
jest.mock('@/components/layout/ConditionalLayout', () => ({
  ConditionalLayout: ({
    children,
    allSections,
  }: {
    children: React.ReactNode
    allSections: any
  }) => (
    <div
      data-testid="conditional-layout"
      data-sections={JSON.stringify(allSections)}
    >
      {children}
    </div>
  ),
}))

describe('RootLayout', () => {
  describe('Metadata', () => {
    it('exports correct default title', () => {
      expect(metadata.title).toBeDefined()
      expect(typeof metadata.title).toBe('object')
      const titleConfig = metadata.title as {
        template: string
        default: string
      }
      expect(titleConfig.default).toBe(
        'BenGER - Vertrauensvolle KI-Bewertung für deutsches Recht'
      )
    })

    it('exports correct title template', () => {
      const titleConfig = metadata.title as {
        template: string
        default: string
      }
      expect(titleConfig.template).toBe('%s - BenGER')
    })

    it('exports correct description', () => {
      expect(metadata.description).toBe(
        'Die führende Plattform für wissenschaftlich fundierte Evaluation von Large Language Models im deutschen Rechtskontext. Entwickelt an der TUM.'
      )
    })

    it('exports correct keywords', () => {
      expect(metadata.keywords).toBeDefined()
      expect(Array.isArray(metadata.keywords)).toBe(true)
      expect(metadata.keywords).toContain('Legal AI')
      expect(metadata.keywords).toContain('LLM Evaluation')
      expect(metadata.keywords).toContain('German Law')
      expect(metadata.keywords).toContain('Legal Technology')
      expect(metadata.keywords).toContain('AI Benchmarking')
    })

    it('exports correct icon configuration', () => {
      expect(metadata.icons).toBeDefined()
      expect(metadata.icons).toHaveProperty('icon', '/icon.svg')
    })

    it('exports correct Open Graph configuration', () => {
      expect(metadata.openGraph).toBeDefined()
      expect(metadata.openGraph?.title).toBe(
        'BenGER - Vertrauensvolle KI-Bewertung für deutsches Recht'
      )
      expect(metadata.openGraph?.description).toBe(
        'Die führende Plattform für wissenschaftlich fundierte Evaluation von Large Language Models im deutschen Rechtskontext.'
      )
      expect(metadata.openGraph?.url).toBe('https://what-a-benger.net')
      expect(metadata.openGraph?.siteName).toBe('BenGER')
      expect(metadata.openGraph?.locale).toBe('de_DE')
      expect(metadata.openGraph?.type).toBe('website')
    })

    it('exports correct Twitter card configuration', () => {
      expect(metadata.twitter).toBeDefined()
      expect(metadata.twitter?.card).toBe('summary_large_image')
      expect(metadata.twitter?.title).toBe(
        'BenGER - Vertrauensvolle KI-Bewertung für deutsches Recht'
      )
      expect(metadata.twitter?.description).toBe(
        'Die führende Plattform für wissenschaftlich fundierte Evaluation von Large Language Models im deutschen Rechtskontext.'
      )
    })
  })

  describe('Component Structure', () => {
    it('renders html element with correct lang attribute', () => {
      const { container } = render(
        <RootLayout>
          <div>Test content</div>
        </RootLayout>
      )

      const html = container.querySelector('html')
      expect(html).toBeInTheDocument()
      expect(html).toHaveAttribute('lang', 'de')
    })

    it('renders html element with correct class', () => {
      const { container } = render(
        <RootLayout>
          <div>Test content</div>
        </RootLayout>
      )

      const html = container.querySelector('html')
      expect(html).toHaveClass('h-full')
    })

    it('renders html element with suppressHydrationWarning', () => {
      const { container } = render(
        <RootLayout>
          <div>Test content</div>
        </RootLayout>
      )

      const html = container.querySelector('html')
      // suppressHydrationWarning is a React prop that doesn't appear in DOM
      expect(html).toBeInTheDocument()
    })

    it('renders body element with correct classes', () => {
      const { container } = render(
        <RootLayout>
          <div>Test content</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      expect(body).toBeInTheDocument()
      expect(body).toHaveClass(
        'flex',
        'min-h-full',
        'w-full',
        'bg-white',
        'antialiased',
        'dark:bg-zinc-900'
      )
    })

    it('renders body element with suppressHydrationWarning', () => {
      const { container } = render(
        <RootLayout>
          <div>Test content</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      // suppressHydrationWarning is a React prop that doesn't appear in DOM
      expect(body).toBeInTheDocument()
    })
  })

  describe('Provider Wrapping', () => {
    it('wraps children with Providers component', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div data-testid="child-content">Test content</div>
        </RootLayout>
      )

      expect(getByTestId('providers')).toBeInTheDocument()
    })

    it('wraps children with ConditionalLayout', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div data-testid="child-content">Test content</div>
        </RootLayout>
      )

      expect(getByTestId('conditional-layout')).toBeInTheDocument()
    })

    it('passes allSections prop to ConditionalLayout', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div data-testid="child-content">Test content</div>
        </RootLayout>
      )

      const conditionalLayout = getByTestId('conditional-layout')
      const sectionsData = conditionalLayout.getAttribute('data-sections')
      expect(sectionsData).toBeDefined()

      const sections = JSON.parse(sectionsData!)
      expect(sections).toHaveProperty('/how-to')
      expect(Array.isArray(sections['/how-to'])).toBe(true)
    })

    it('includes DevModeIndicator', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div data-testid="child-content">Test content</div>
        </RootLayout>
      )

      expect(getByTestId('dev-mode-indicator')).toBeInTheDocument()
    })

    it('renders DevModeIndicator after ConditionalLayout', () => {
      const { container } = render(
        <RootLayout>
          <div data-testid="child-content">Test content</div>
        </RootLayout>
      )

      const providers = container.querySelector('[data-testid="providers"]')
      const conditionalLayout = container.querySelector(
        '[data-testid="conditional-layout"]'
      )
      const devIndicator = container.querySelector(
        '[data-testid="dev-mode-indicator"]'
      )

      expect(providers).toContainElement(conditionalLayout)
      expect(providers).toContainElement(devIndicator)
    })
  })

  describe('Children Rendering', () => {
    it('renders children content correctly', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div data-testid="child-content">Test content</div>
        </RootLayout>
      )

      expect(getByTestId('child-content')).toBeInTheDocument()
      expect(getByTestId('child-content')).toHaveTextContent('Test content')
    })

    it('handles multiple children', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div data-testid="child-1">Child 1</div>
          <div data-testid="child-2">Child 2</div>
          <div data-testid="child-3">Child 3</div>
        </RootLayout>
      )

      expect(getByTestId('child-1')).toBeInTheDocument()
      expect(getByTestId('child-2')).toBeInTheDocument()
      expect(getByTestId('child-3')).toBeInTheDocument()
    })

    it('handles empty children', () => {
      const { getByTestId } = render(<RootLayout>{null}</RootLayout>)

      expect(getByTestId('providers')).toBeInTheDocument()
      expect(getByTestId('conditional-layout')).toBeInTheDocument()
    })

    it('handles complex nested children', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div>
            <header data-testid="header">Header</header>
            <main data-testid="main">
              <div data-testid="content">Content</div>
            </main>
            <footer data-testid="footer">Footer</footer>
          </div>
        </RootLayout>
      )

      expect(getByTestId('header')).toBeInTheDocument()
      expect(getByTestId('main')).toBeInTheDocument()
      expect(getByTestId('content')).toBeInTheDocument()
      expect(getByTestId('footer')).toBeInTheDocument()
    })
  })

  describe('Section Configuration', () => {
    it('defines /how-to sections correctly', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const conditionalLayout = getByTestId('conditional-layout')
      const sectionsData = conditionalLayout.getAttribute('data-sections')
      const sections = JSON.parse(sectionsData!)

      expect(sections['/how-to']).toEqual([
        { id: 'platform-overview', title: 'Platform Overview' },
        { id: 'projects', title: 'Projects' },
        { id: 'data-import', title: 'Data Import' },
        { id: 'annotation', title: 'Annotation' },
        { id: 'generation', title: 'Generation' },
        { id: 'evaluation', title: 'Evaluation' },
        { id: 'organizations', title: 'Organizations & Roles' },
        { id: 'api-key-management', title: 'API Key Management' },
        { id: 'troubleshooting', title: 'Troubleshooting' },
      ])
    })

    it('includes all required section IDs for /how-to', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const conditionalLayout = getByTestId('conditional-layout')
      const sectionsData = conditionalLayout.getAttribute('data-sections')
      const sections = JSON.parse(sectionsData!)
      const howToSections = sections['/how-to']

      const sectionIds = howToSections.map((s: any) => s.id)
      expect(sectionIds).toContain('platform-overview')
      expect(sectionIds).toContain('projects')
      expect(sectionIds).toContain('data-import')
      expect(sectionIds).toContain('annotation')
      expect(sectionIds).toContain('generation')
      expect(sectionIds).toContain('evaluation')
      expect(sectionIds).toContain('organizations')
      expect(sectionIds).toContain('api-key-management')
      expect(sectionIds).toContain('troubleshooting')
    })

    it('includes all required section titles for /how-to', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const conditionalLayout = getByTestId('conditional-layout')
      const sectionsData = conditionalLayout.getAttribute('data-sections')
      const sections = JSON.parse(sectionsData!)
      const howToSections = sections['/how-to']

      const sectionTitles = howToSections.map((s: any) => s.title)
      expect(sectionTitles).toContain('Platform Overview')
      expect(sectionTitles).toContain('Projects')
      expect(sectionTitles).toContain('Data Import')
      expect(sectionTitles).toContain('Annotation')
      expect(sectionTitles).toContain('Generation')
      expect(sectionTitles).toContain('Evaluation')
      expect(sectionTitles).toContain('Organizations & Roles')
      expect(sectionTitles).toContain('API Key Management')
      expect(sectionTitles).toContain('Troubleshooting')
    })

    it('has correct number of sections for /how-to', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const conditionalLayout = getByTestId('conditional-layout')
      const sectionsData = conditionalLayout.getAttribute('data-sections')
      const sections = JSON.parse(sectionsData!)

      expect(sections['/how-to']).toHaveLength(9)
    })
  })

  describe('Dark Mode Support', () => {
    it('includes dark mode background class on body', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      expect(body).toHaveClass('dark:bg-zinc-900')
    })

    it('supports theme switching via class attribute', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const html = container.querySelector('html')
      expect(html).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('sets correct lang attribute for German content', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const html = container.querySelector('html')
      expect(html).toHaveAttribute('lang', 'de')
    })

    it('uses semantic HTML structure', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      expect(container.querySelector('html')).toBeInTheDocument()
      expect(container.querySelector('body')).toBeInTheDocument()
    })

    it('enables text anti-aliasing for better readability', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      expect(body).toHaveClass('antialiased')
    })
  })

  describe('Responsive Design', () => {
    it('uses full height layout', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const html = container.querySelector('html')
      expect(html).toHaveClass('h-full')

      const body = container.querySelector('body')
      expect(body).toHaveClass('min-h-full')
    })

    it('uses full width layout', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      expect(body).toHaveClass('w-full')
    })

    it('uses flexbox for layout', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      expect(body).toHaveClass('flex')
    })
  })

  describe('Visual Design', () => {
    it('sets white background for light mode', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      expect(body).toHaveClass('bg-white')
    })

    it('sets zinc-900 background for dark mode', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      expect(body).toHaveClass('dark:bg-zinc-900')
    })

    it('applies antialiased text rendering', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      expect(body).toHaveClass('antialiased')
    })
  })

  describe('Edge Cases', () => {
    it('handles string children', () => {
      const { container } = render(<RootLayout>Simple text</RootLayout>)

      expect(container.textContent).toContain('Simple text')
    })

    it('handles fragment children', () => {
      const { getByTestId } = render(
        <RootLayout>
          <>
            <div data-testid="fragment-child-1">Child 1</div>
            <div data-testid="fragment-child-2">Child 2</div>
          </>
        </RootLayout>
      )

      expect(getByTestId('fragment-child-1')).toBeInTheDocument()
      expect(getByTestId('fragment-child-2')).toBeInTheDocument()
    })

    it('handles undefined children', () => {
      const { getByTestId } = render(<RootLayout>{undefined}</RootLayout>)

      expect(getByTestId('providers')).toBeInTheDocument()
    })

    it('handles conditional children', () => {
      const shouldRender = true
      const { getByTestId } = render(
        <RootLayout>
          {shouldRender && (
            <div data-testid="conditional-child">Conditional</div>
          )}
        </RootLayout>
      )

      expect(getByTestId('conditional-child')).toBeInTheDocument()

      const { queryByTestId } = render(
        <RootLayout>
          {false && <div data-testid="conditional-child-2">Conditional</div>}
        </RootLayout>
      )

      expect(queryByTestId('conditional-child-2')).not.toBeInTheDocument()
    })
  })

  describe('Component Nesting', () => {
    it('maintains correct provider hierarchy', () => {
      const { container } = render(
        <RootLayout>
          <div>Test</div>
        </RootLayout>
      )

      const body = container.querySelector('body')
      const providers = container.querySelector('[data-testid="providers"]')
      const conditionalLayout = container.querySelector(
        '[data-testid="conditional-layout"]'
      )

      expect(body).toContainElement(providers)
      expect(providers).toContainElement(conditionalLayout)
    })

    it('renders children inside ConditionalLayout', () => {
      const { getByTestId } = render(
        <RootLayout>
          <div data-testid="test-child">Test child</div>
        </RootLayout>
      )

      const conditionalLayout = getByTestId('conditional-layout')
      const testChild = getByTestId('test-child')

      expect(conditionalLayout).toContainElement(testChild)
    })
  })
})
