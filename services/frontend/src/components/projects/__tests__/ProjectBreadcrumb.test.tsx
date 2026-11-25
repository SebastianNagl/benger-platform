/**
 * @jest-environment jsdom
 *
 * ProjectBreadcrumb: the trail of every project page (dashboard, projects,
 * the project by its title, then the page), with the project read when the
 * store holds none or another one.
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor, within } from '@testing-library/react'

import { ProjectBreadcrumb } from '../ProjectBreadcrumb'

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock('de'),
)

const mockFetchProject = jest.fn()
let mockCurrentProject: { id: string; title: string } | null = null
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    currentProject: mockCurrentProject,
    fetchProject: mockFetchProject,
  }),
}))

beforeEach(() => {
  jest.clearAllMocks()
  mockCurrentProject = { id: 'p1', title: 'Projekt Eins' }
})

function trail() {
  return within(
    screen.getByRole('navigation', { name: 'Brotkrümelnavigation' }),
  )
}

describe('ProjectBreadcrumb', () => {
  it('leads from the dashboard over the project to the page', () => {
    render(
      <ProjectBreadcrumb
        projectId="p1"
        items={[
          { label: 'Daten', href: '/projects/p1/data' },
          { label: 'Aufgabe 3' },
        ]}
      />,
    )
    const links = trail().getAllByRole('link')
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/dashboard',
      '/projects',
      '/projects/p1',
      '/projects/p1/data',
    ])
    expect(links[1]).toHaveTextContent('Projekte')
    expect(links[2]).toHaveTextContent('Projekt Eins')
    // The current page is plain text, not a link.
    expect(trail().getByText('Aufgabe 3').closest('a')).toBeNull()
    expect(mockFetchProject).not.toHaveBeenCalled()
  })

  it('ends on the project itself when the page adds no crumbs', () => {
    render(<ProjectBreadcrumb projectId="p1" />)
    expect(trail().getAllByRole('link')).toHaveLength(2)
    expect(trail().getByText('Projekt Eins').closest('a')).toBeNull()
  })

  it('reads the project when the store holds none, with a placeholder meanwhile', () => {
    mockCurrentProject = null
    mockFetchProject.mockReturnValue(new Promise(() => {}))
    render(<ProjectBreadcrumb projectId="p1" items={[{ label: 'Seite' }]} />)
    // Not the id: a long id wraps the trail, which the title then undoes.
    expect(trail().queryByText('p1')).not.toBeInTheDocument()
    expect(
      trail().getByRole('link', { name: 'Projekt wird geladen...' }),
    ).toHaveAttribute('href', '/projects/p1')
    expect(screen.getByTestId('project-breadcrumb-pending')).toBeInTheDocument()
    expect(mockFetchProject).toHaveBeenCalledTimes(1)
    expect(mockFetchProject).toHaveBeenCalledWith('p1', { shared: true })
  })

  it('falls back to the id when the read fails', async () => {
    mockCurrentProject = null
    mockFetchProject.mockResolvedValue(null)
    render(<ProjectBreadcrumb projectId="p1" items={[{ label: 'Seite' }]} />)
    await waitFor(() =>
      expect(trail().getByRole('link', { name: 'p1' })).toHaveAttribute(
        'href',
        '/projects/p1',
      ),
    )
  })

  it('never shows the title of another project', () => {
    mockCurrentProject = { id: 'p2', title: 'Anderes Projekt' }
    mockFetchProject.mockReturnValue(new Promise(() => {}))
    render(<ProjectBreadcrumb projectId="p1" items={[{ label: 'Seite' }]} />)
    expect(trail().queryByText('Anderes Projekt')).not.toBeInTheDocument()
    expect(screen.getByTestId('project-breadcrumb-pending')).toBeInTheDocument()
    expect(mockFetchProject).toHaveBeenCalledWith('p1', { shared: true })
  })

  it('takes a title the page already knows and leaves the store alone', () => {
    mockCurrentProject = { id: 'p2', title: 'Anderes Projekt' }
    render(
      <ProjectBreadcrumb
        projectId="p1"
        projectTitle="Aus dem Bericht"
        items={[{ label: 'Seite' }]}
      />,
    )
    expect(
      trail().getByRole('link', { name: 'Aus dem Bericht' }),
    ).toHaveAttribute('href', '/projects/p1')
    expect(mockFetchProject).not.toHaveBeenCalled()
  })

  it('matches a numeric store id against the route id', () => {
    mockCurrentProject = { id: 7 as unknown as string, title: 'Sieben' }
    render(<ProjectBreadcrumb projectId="7" items={[{ label: 'Seite' }]} />)
    expect(trail().getByRole('link', { name: 'Sieben' })).toBeInTheDocument()
    expect(mockFetchProject).not.toHaveBeenCalled()
  })
})
