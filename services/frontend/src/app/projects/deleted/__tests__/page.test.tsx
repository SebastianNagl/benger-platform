/**
 * @jest-environment jsdom
 *
 * /projects/deleted — superadmin-only soft-delete recovery view: lists
 * deleted projects, restores, and (only here) purges for good.
 */
import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import DeletedProjectsPage from '../page'

const mockReplace = jest.fn()
jest.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mockReplace, push: jest.fn() }),
}))
const mockUser = { current: { id: 'a', is_superadmin: true } as any }
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: mockUser.current, isLoading: false }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (k: string, d?: any, vars?: any) => {
      let s = typeof d === 'string' ? d : k
      const v = vars ?? (typeof d === 'object' ? d : undefined)
      if (v) for (const key of Object.keys(v)) s = s.split(`{${key}}`).join(String(v[key]))
      return s
    },
  }),
}))
jest.mock('@/components/shared/Breadcrumb', () => ({
  Breadcrumb: () => <nav />,
}))
jest.mock('@/components/shared/ResponsiveContainer', () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}))
const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({ useToast: () => ({ addToast: mockAddToast }) }))
const mockConfirm = jest.fn()
jest.mock('@/hooks/useDialogs', () => ({ useConfirm: () => mockConfirm }))
const mockList = jest.fn()
const mockRestore = jest.fn()
const mockPurge = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    list: (...a: any[]) => mockList(...a),
    restoreProject: (...a: any[]) => mockRestore(...a),
    purgeProject: (...a: any[]) => mockPurge(...a),
  },
}))

const row = { id: 'p1', title: 'Alte Klausur', kind: 'exam', deleted_at: '2026-08-24T10:00:00Z' }

describe('DeletedProjectsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockUser.current = { id: 'a', is_superadmin: true }
    mockList.mockResolvedValue({ items: [row] })
  })

  it('lists deleted projects with only_deleted and restores', async () => {
    mockRestore.mockResolvedValue(undefined)
    render(<DeletedProjectsPage />)
    expect(await screen.findByTestId('deleted-row-p1')).toHaveTextContent('Alte Klausur')
    expect(mockList).toHaveBeenCalledWith(1, 200, undefined, undefined, undefined, true)
    mockList.mockResolvedValue({ items: [] })
    fireEvent.click(screen.getByTestId('deleted-restore-p1'))
    await waitFor(() => expect(mockRestore).toHaveBeenCalledWith('p1'))
    expect(await screen.findByTestId('deleted-empty')).toBeInTheDocument()
  })

  it('purge asks a danger confirm and only proceeds on yes', async () => {
    mockConfirm.mockResolvedValueOnce(false)
    render(<DeletedProjectsPage />)
    fireEvent.click(await screen.findByTestId('deleted-purge-p1'))
    await waitFor(() => expect(mockConfirm).toHaveBeenCalled())
    expect(mockConfirm.mock.calls[0][0]).toMatchObject({ variant: 'danger' })
    expect(mockConfirm.mock.calls[0][0].message).toContain('Alte Klausur')
    expect(mockPurge).not.toHaveBeenCalled()
    mockConfirm.mockResolvedValueOnce(true)
    mockPurge.mockResolvedValue(undefined)
    fireEvent.click(screen.getByTestId('deleted-purge-p1'))
    await waitFor(() => expect(mockPurge).toHaveBeenCalledWith('p1'))
  })

  it('non-superadmins are redirected away', async () => {
    mockUser.current = { id: 'b', is_superadmin: false }
    render(<DeletedProjectsPage />)
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/projects'))
    expect(mockList).not.toHaveBeenCalled()
  })
})
