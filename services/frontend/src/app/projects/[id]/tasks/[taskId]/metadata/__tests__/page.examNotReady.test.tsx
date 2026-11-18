/**
 * The task metadata page reads the same gated task endpoint: a 403
 * `{code: "exam_not_ready"}` shows the localized "not released yet" notice,
 * any other failure keeps "task not found" and its toast.
 */

import apiClient from '@/lib/api'
import { useProjectStore } from '@/stores/projectStore'
import { EXAM_NOT_READY, NOTICE, apiError } from '@/test-utils/examNotReady'
import { mockToast } from '@/test-utils/setupTests'
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { useRouter } from 'next/navigation'
import TaskMetadataPage from '../page'

let mockLocale: 'de' | 'en' | 'fr' = 'en'

jest.mock('next/navigation', () => ({ useRouter: jest.fn() }))
jest.mock('@/stores/projectStore', () => ({ useProjectStore: jest.fn() }))
jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn() },
}))
jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock(() => mockLocale),
)

function renderPage() {
  // The page unwraps its params with React.use(); a promise already marked
  // fulfilled is read synchronously, without suspending.
  const value = { id: 'exam-1', taskId: 'task-1' }
  const params = Object.assign(Promise.resolve(value), {
    status: 'fulfilled',
    value,
  })
  return render(<TaskMetadataPage params={params} />)
}

describe('TaskMetadataPage: exam not released yet', () => {
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
      ;(apiClient.get as jest.Mock).mockRejectedValue(EXAM_NOT_READY)

      renderPage()

      expect(await screen.findByTestId('exam-not-ready')).toBeInTheDocument()
      expect(screen.getByText(NOTICE[locale].title)).toBeInTheDocument()
      expect(screen.getByText(NOTICE[locale].description)).toBeInTheDocument()
      expect(mockToast.addToast).not.toHaveBeenCalled()
    },
  )

  it.each([
    ['another 403', apiError(403, 'Not enough permissions')],
    ['a 404', apiError(404, 'Task not found')],
  ])('keeps "task not found" for %s', async (_label, error) => {
    ;(apiClient.get as jest.Mock).mockRejectedValue(error)

    renderPage()

    expect(await screen.findByText('Task not found')).toBeInTheDocument()
    expect(screen.queryByTestId('exam-not-ready')).not.toBeInTheDocument()
    expect(mockToast.addToast).toHaveBeenCalledWith(
      'Failed to load task',
      'error',
    )
  })
})
