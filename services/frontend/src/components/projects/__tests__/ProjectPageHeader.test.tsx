/**
 * @jest-environment jsdom
 *
 * ProjectPageHeader: breadcrumb, title in the standard style, description,
 * badge and actions of a page under a project.
 */
import '@testing-library/jest-dom'
import { render, screen, within } from '@testing-library/react'

import { ProjectPageHeader } from '../ProjectPageHeader'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('en'),
)

const mockFetchProject = jest.fn()
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    currentProject: { id: 'p1', title: 'Project One' },
    fetchProject: mockFetchProject,
  }),
}))

describe('ProjectPageHeader', () => {
  it('renders the trail, the title and the description', () => {
    render(
      <ProjectPageHeader
        projectId="p1"
        breadcrumbs={[{ label: 'Data', href: '/projects/p1/data' }]}
        title="Project data"
        description="Project One"
      />,
    )
    const nav = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(
      within(nav).getByRole('link', { name: 'Project One' }),
    ).toHaveAttribute('href', '/projects/p1')
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('Project data')
    expect(heading).toHaveClass('text-3xl', 'font-bold', 'tracking-tight')
    expect(screen.getAllByText('Project One')).toHaveLength(2)
  })

  it('places the badge next to the title and the actions beside it', () => {
    render(
      <ProjectPageHeader
        projectId="p1"
        title="Review"
        badge={<span>Blind</span>}
        actions={<button type="button">Export</button>}
        data-testid="page-header"
      >
        <p>Snapshot from today</p>
      </ProjectPageHeader>,
    )
    const header = screen.getByTestId('page-header')
    const heading = within(header).getByRole('heading', { level: 1 })
    expect(heading.parentElement).toContainElement(screen.getByText('Blind'))
    expect(
      within(header).getByRole('button', { name: 'Export' }),
    ).toBeInTheDocument()
    expect(within(header).getByText('Snapshot from today')).toBeInTheDocument()
  })

  it('leaves out the description and the actions row when not given', () => {
    const { container } = render(
      <ProjectPageHeader projectId="p1" title="Plain" />,
    )
    expect(container.querySelectorAll('p')).toHaveLength(0)
    const row = screen
      .getByRole('heading', { level: 1 })
      .closest('.justify-between')
    expect(row?.children).toHaveLength(1)
  })

  it('passes a known project title on to the breadcrumb', () => {
    render(
      <ProjectPageHeader
        projectId="p9"
        projectTitle="From the report"
        breadcrumbs={[{ label: 'Report' }]}
        title="Report"
      />,
    )
    expect(
      screen.getByRole('link', { name: 'From the report' }),
    ).toHaveAttribute('href', '/projects/p9')
    expect(mockFetchProject).not.toHaveBeenCalled()
  })
})
