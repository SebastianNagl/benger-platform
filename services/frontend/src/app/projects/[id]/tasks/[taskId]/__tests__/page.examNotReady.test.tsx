/**
 * A participant opening a task page of an exam the server holds closed
 * (403 `{code: "exam_not_ready"}` until its grading sheet is checked) sees
 * the localized "not released yet" notice, not "Task not found ... has been
 * deleted". Other refusals keep the current "not found" page and toast.
 */

import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { EXAM_NOT_READY, NOTICE, apiError } from '@/test-utils/examNotReady'
import { mockToast } from '@/test-utils/setupTests'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import TaskDetailPage from '../page'

let mockLocale: 'de' | 'en' | 'fr' = 'en'

jest.mock('next/navigation', () => ({ useRouter: jest.fn() }))
jest.mock('@/stores/projectStore', () => ({ useProjectStore: jest.fn() }))
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: { getTask: jest.fn() },
}))
jest.mock('@/components/auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: any) => <>{children}</>,
}))
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock(() => mockLocale),
)

const NOT_FOUND = {
  title: 'Task not found',
  description: "The task you're looking for doesn't exist or has been deleted.",
}

function renderPage() {
  const params = Promise.resolve({ id: 'exam-1', taskId: 'task-1' })
  return render(<TaskDetailPage params={params} />)
}

describe('TaskDetailPage: exam not released yet', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockLocale = 'en'
    ;(useRouter as jest.Mock).mockReturnValue({ push: jest.fn() })
    ;(useProjectStore as unknown as jest.Mock).mockReturnValue({
      currentProject: { id: 'exam-1', title: 'Klausur' },
      fetchProject: jest.fn(),
    })
  })

  it.each(['de', 'en', 'fr'] as const)(
    'shows the localized notice for a 403 exam_not_ready (%s)',
    async (locale) => {
      mockLocale = locale
      ;(projectsAPI.getTask as jest.Mock).mockRejectedValue(EXAM_NOT_READY)

      renderPage()

      expect(await screen.findByTestId('exam-not-ready')).toBeInTheDocument()
      expect(screen.getByText(NOTICE[locale].title)).toBeInTheDocument()
      expect(screen.getByText(NOTICE[locale].description)).toBeInTheDocument()
      expect(screen.queryByText(/not found|nicht gefunden|introuvable/i)).toBe(
        null,
      )
      expect(mockToast.addToast).not.toHaveBeenCalled()
    },
  )

  it.each([
    ['another 403', apiError(403, 'Not enough permissions')],
    [
      'a 403 with another code',
      apiError(403, { code: 'project_window_upcoming' }),
    ],
    ['a 404', apiError(404, 'Task not found')],
  ])('keeps "task not found" for %s', async (_label, error) => {
    ;(projectsAPI.getTask as jest.Mock).mockRejectedValue(error)

    renderPage()

    expect(await screen.findByText(NOT_FOUND.title)).toBeInTheDocument()
    expect(screen.getByText(NOT_FOUND.description)).toBeInTheDocument()
    expect(screen.queryByTestId('exam-not-ready')).not.toBeInTheDocument()
    expect(mockToast.addToast).toHaveBeenCalledWith(
      'Failed to load task',
      'error',
    )
  })
})
