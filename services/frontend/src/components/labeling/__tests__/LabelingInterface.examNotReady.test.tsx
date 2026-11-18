/**
 * @jest-environment jsdom
 *
 * A participant opening /projects/<id>/label of an exam the server holds
 * closed (403 `{code: "exam_not_ready"}` on the task reads, until its grading
 * sheet is checked) sees the localized "not released yet" notice, not the
 * "Initialization error: no tasks available" screen. Runs the real project
 * store against a mocked API, so the path from the refused read to the page
 * is covered end to end. Other refusals keep their current messages.
 */

import { projectsAPI } from '@/lib/api/projects'
import { useProjectStore } from '@/stores/projectStore'
import { EXAM_NOT_READY, NOTICE, apiError } from '@/test-utils/examNotReady'
import { mockToast } from '@/test-utils/setupTests'
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { useRouter, useSearchParams } from 'next/navigation'
import { LabelingInterface } from '../LabelingInterface'

let mockLocale: 'de' | 'en' | 'fr' = 'en'

jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
  useSearchParams: jest.fn(),
}))

jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    get: jest.fn(),
    getTasks: jest.fn(),
    getNextTask: jest.fn(),
    getTaskAnnotations: jest.fn().mockResolvedValue([]),
  },
}))

jest.mock('../DynamicAnnotationInterface', () => ({
  DynamicAnnotationInterface: () => <div data-testid="annotation-editor" />,
}))

jest.mock('@/contexts/I18nContext', () =>
  require('@/test-utils/i18nMock').i18nMock(() => mockLocale),
)

const PROJECT = {
  id: 'exam-1',
  title: 'Klausur Zivilrecht',
  label_config: '<View><Text name="text" value="$text"/></View>',
  assignment_mode: 'open',
}

const initialStore = useProjectStore.getState()

describe('LabelingInterface: exam not released yet', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockLocale = 'en'
    useProjectStore.setState(initialStore, true)
    window.localStorage.clear()
    ;(useRouter as jest.Mock).mockReturnValue({ push: jest.fn() })
    ;(useSearchParams as jest.Mock).mockReturnValue({ get: () => null })
    ;(projectsAPI.get as jest.Mock).mockResolvedValue(PROJECT)
  })

  it.each(['de', 'en', 'fr'] as const)(
    'shows the localized notice for a 403 exam_not_ready (%s)',
    async (locale) => {
      mockLocale = locale
      ;(projectsAPI.getTasks as jest.Mock).mockRejectedValue(EXAM_NOT_READY)
      ;(projectsAPI.getNextTask as jest.Mock).mockRejectedValue(EXAM_NOT_READY)

      render(<LabelingInterface projectId="exam-1" />)

      expect(await screen.findByTestId('exam-not-ready')).toBeInTheDocument()
      expect(
        screen.queryByText(NOTICE[locale].formerTitle),
      ).not.toBeInTheDocument()
      expect(screen.getByText(NOTICE[locale].description)).toBeInTheDocument()
      expect(screen.queryByText(/Initiali[sz]ation/i)).not.toBeInTheDocument()
      expect(
        screen.queryByText(/Initialisierungsfehler/),
      ).not.toBeInTheDocument()
      // Neither the server's English message nor "no tasks" is toasted.
      expect(mockToast.addToast).not.toHaveBeenCalled()
      // The refused list already answers it; /next is not asked as well.
      expect(projectsAPI.getNextTask).not.toHaveBeenCalled()
    },
  )

  it('shows the notice when /next refuses an auto-assigned exam', async () => {
    ;(projectsAPI.get as jest.Mock).mockResolvedValue({
      ...PROJECT,
      assignment_mode: 'auto',
    })
    ;(projectsAPI.getNextTask as jest.Mock).mockRejectedValue(EXAM_NOT_READY)

    render(<LabelingInterface projectId="exam-1" />)

    expect(await screen.findByTestId('exam-not-ready')).toBeInTheDocument()
    expect(screen.getByText(NOTICE.en.description)).toBeInTheDocument()
    expect(mockToast.addToast).not.toHaveBeenCalled()
  })

  it('keeps the initialization error for an exam with no tasks', async () => {
    ;(projectsAPI.getTasks as jest.Mock).mockResolvedValue([])
    ;(projectsAPI.getNextTask as jest.Mock).mockResolvedValue({ task: null })

    render(<LabelingInterface projectId="exam-1" />)

    expect(
      await screen.findByText(
        'No tasks are available for annotation in this project.',
      ),
    ).toBeInTheDocument()
    expect(screen.getByText('Initialization Error')).toBeInTheDocument()
    expect(screen.queryByTestId('exam-not-ready')).not.toBeInTheDocument()
  })

  it.each([
    [
      'another 403',
      apiError(403, 'Not enough permissions', 'Not enough permissions'),
    ],
    [
      'a 403 with another code',
      apiError(
        403,
        { code: 'project_window_upcoming', message: 'Not open yet.' },
        'Not open yet.',
      ),
    ],
    ['a 404', apiError(404, 'Project not found', 'Project not found')],
  ])('keeps the current messages for %s', async (_label, error) => {
    ;(projectsAPI.getTasks as jest.Mock).mockRejectedValue(error)
    ;(projectsAPI.getNextTask as jest.Mock).mockRejectedValue(error)

    render(<LabelingInterface projectId="exam-1" />)

    expect(
      await screen.findByText(
        'No tasks are available for annotation in this project.',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('exam-not-ready')).not.toBeInTheDocument()
    await waitFor(() =>
      expect(mockToast.addToast).toHaveBeenCalledWith(error.message, 'error'),
    )
  })
})
