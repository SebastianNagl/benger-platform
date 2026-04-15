/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import HowToPage from '../page'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

jest.mock('@/components/shared', () => ({
  HeroPattern: () => <div data-testid="hero-pattern" />,
}))

jest.mock('@/components/howto', () => ({
  HowToSection: ({ children, title, id }: any) => (
    <section data-testid={`section-${id}`}>
      <h2>{title}</h2>
      {children}
    </section>
  ),
}))

describe('HowToPage', () => {
  it('should render the page title', () => {
    render(<HowToPage />)
    expect(screen.getByText('howTo.title')).toBeInTheDocument()
  })

  it('should render the subtitle', () => {
    render(<HowToPage />)
    expect(screen.getByText('howTo.subtitle')).toBeInTheDocument()
  })

  it('should render HeroPattern', () => {
    render(<HowToPage />)
    expect(screen.getByTestId('hero-pattern')).toBeInTheDocument()
  })

  it('should render platform overview section', () => {
    render(<HowToPage />)
    expect(screen.getByTestId('section-platform-overview')).toBeInTheDocument()
    expect(
      screen.getByText('howTo.sections.platformOverview.title')
    ).toBeInTheDocument()
  })

  it('should render projects section', () => {
    render(<HowToPage />)
    expect(screen.getByTestId('section-projects')).toBeInTheDocument()
    expect(screen.getByText('howTo.sections.projects.title')).toBeInTheDocument()
  })

  it('should render annotation section', () => {
    render(<HowToPage />)
    expect(screen.getByTestId('section-annotation')).toBeInTheDocument()
    expect(screen.getByText('howTo.sections.annotation.title')).toBeInTheDocument()
  })

  it('should render workflow steps in platform overview', () => {
    render(<HowToPage />)
    expect(
      screen.getByText('howTo.sections.platformOverview.workflow.title')
    ).toBeInTheDocument()
    expect(
      screen.getByText('howTo.sections.platformOverview.workflow.description')
    ).toBeInTheDocument()

    // Should render all 6 workflow steps
    for (const step of ['step1', 'step2', 'step3', 'step4', 'step5', 'step6']) {
      expect(
        screen.getByText(`howTo.sections.platformOverview.workflow.${step}.title`)
      ).toBeInTheDocument()
      expect(
        screen.getByText(`howTo.sections.platformOverview.workflow.${step}.description`)
      ).toBeInTheDocument()
    }
  })

  it('should render navigation groups', () => {
    render(<HowToPage />)
    for (const group of ['quickStart', 'projectsAndData', 'knowledge']) {
      expect(
        screen.getByText(`howTo.sections.platformOverview.navigation.${group}.title`)
      ).toBeInTheDocument()
      expect(
        screen.getByText(
          `howTo.sections.platformOverview.navigation.${group}.description`
        )
      ).toBeInTheDocument()
    }
  })

  it('should render project creation steps', () => {
    render(<HowToPage />)
    expect(
      screen.getByText('howTo.sections.projects.creating.title')
    ).toBeInTheDocument()
    for (const step of ['step1', 'step2', 'step3']) {
      expect(
        screen.getByText(`howTo.sections.projects.creating.${step}.title`)
      ).toBeInTheDocument()
    }
  })

  it('should render project templates', () => {
    render(<HowToPage />)
    for (const tmpl of ['qa', 'multipleChoice', 'examSolving', 'spanAnnotation']) {
      expect(
        screen.getByText(`howTo.sections.projects.templates.${tmpl}.title`)
      ).toBeInTheDocument()
      expect(
        screen.getByText(`howTo.sections.projects.templates.${tmpl}.description`)
      ).toBeInTheDocument()
    }
  })

  it('should render evaluation section', () => {
    render(<HowToPage />)
    expect(screen.getByTestId('section-evaluation')).toBeInTheDocument()
    expect(screen.getByText('howTo.sections.evaluation.title')).toBeInTheDocument()
  })

  it('should render generation section', () => {
    render(<HowToPage />)
    expect(screen.getByTestId('section-generation')).toBeInTheDocument()
    expect(screen.getByText('howTo.sections.generation.title')).toBeInTheDocument()
  })

  it('should render organizations section', () => {
    render(<HowToPage />)
    expect(screen.getByTestId('section-organizations')).toBeInTheDocument()
    expect(
      screen.getByText('howTo.sections.organizations.title')
    ).toBeInTheDocument()
  })
})
