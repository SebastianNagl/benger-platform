/**
 * "Entdecken" button + discover modal slot, participant / deck badges and
 * row actions on the projects list.
 *
 * @jest-environment jsdom
 */

import { registerSlot } from '@/lib/extensions/slots'
import { useProjectStore } from '@/stores/projectStore'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import { ProjectListTable } from '../ProjectListTable'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({ push: jest.fn() })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn(),
}))
jest.mock('@/stores/projectStore', () => ({ useProjectStore: jest.fn() }))
jest.mock('@/lib/api/projects', () => ({ projectsAPI: {} }))
jest.mock('@/hooks/useDialogs', () => ({ useConfirm: () => jest.fn() }))
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn(), removeToast: jest.fn() }),
}))
jest.mock('@/contexts/ProgressContext', () => ({
  useProgress: () => ({ startProgress: jest.fn(), updateProgress: jest.fn(), completeProgress: jest.fn() }),
}))
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1', is_superadmin: false, role: 'ANNOTATOR' },
    isAuthenticated: true,
    isLoading: false,
  }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string, def?: any) => (typeof def === 'string' ? def : key), locale: 'de' }),
}))

const project = (o: any = {}) => ({
  id: 'p1',
  title: 'Probeklausur',
  created_by: 'owner',
  created_at: '2026-08-01T00:00:00Z',
  is_public: false,
  enable_annotation: true,
  task_count: 2,
  completed_tasks_count: 0,
  ...o,
})

const store = (projects: any[]) => ({
  projects,
  loading: false,
  fetchProjects: jest.fn(),
  setSearchQuery: jest.fn(),
  searchQuery: '',
  currentPage: 1,
  pageSize: 25,
  totalProjects: projects.length,
  totalPages: 1,
  setCurrentPage: jest.fn(),
  setPageSize: jest.fn(),
})

describe('ProjectListTable — discover + participant', () => {
  const push = jest.fn()
  beforeEach(() => {
    jest.clearAllMocks()
    ;(useRouter as jest.Mock).mockReturnValue({ push })
    registerSlot('ProjectDiscoverModal', null as any)
  })

  it('has no Entdecken button without the slot', () => {
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(store([]))
    render(<ProjectListTable />)
    expect(screen.queryByTestId('projects-discover-button')).not.toBeInTheDocument()
  })

  it('opens the discover modal and on join refetches + navigates', async () => {
    const Modal = jest.fn(({ isOpen, onJoined, onClose }: any) =>
      isOpen ? (
        <div data-testid="discover-modal">
          <button onClick={() => onJoined('joined-1')}>join</button>
          <button onClick={onClose}>close</button>
        </div>
      ) : null,
    )
    registerSlot('ProjectDiscoverModal', Modal)
    const s = store([])
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(s)
    render(<ProjectListTable />)
    // Not gated on create permissions (annotator-role users browse too).
    fireEvent.click(screen.getByTestId('projects-more-button'))
    fireEvent.click(screen.getByTestId('projects-discover-button'))
    expect(await screen.findByTestId('discover-modal')).toBeInTheDocument()
    s.fetchProjects.mockClear()
    fireEvent.click(screen.getByText('join'))
    await waitFor(() => expect(push).toHaveBeenCalledWith('/projects/joined-1'))
    expect(s.fetchProjects).toHaveBeenCalled()
    expect(screen.queryByTestId('discover-modal')).not.toBeInTheDocument()
  })

  it('renders the participant badge, hides the checkbox, and a deck badge with Lernen', () => {
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue(
      store([
        project({ id: 'p1', access_tier: 'participant', participant_via: 'share' }),
        project({ id: 'd1', kind: 'flashcard_collection', access_tier: 'full' }),
      ]),
    )
    render(<ProjectListTable />)
    expect(screen.getByTestId('project-participant-badge-p1')).toHaveTextContent('Teilnehmer')
    expect(screen.getByTestId('project-participant-badge-p1')).toHaveAttribute(
      'title',
      'Beigetreten',
    )
    expect(screen.queryByTestId('projects-table-checkbox-p1')).not.toBeInTheDocument()
    expect(screen.getByTestId('project-kind-badge-d1')).toHaveTextContent('Kartenstapel')
    fireEvent.click(screen.getByTestId('project-study-d1'))
    expect(push).toHaveBeenCalledWith('/projects/d1')
  })
})
