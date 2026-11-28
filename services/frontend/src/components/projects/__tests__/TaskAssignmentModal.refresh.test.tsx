/**
 * @jest-environment jsdom
 *
 * Assigning tasks after the access token expired: the request goes through
 * the API client, which refreshes the token once and retries, so the
 * manager sees the assignment succeed instead of "assign failed".
 */

import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TaskAssignmentModal } from '../TaskAssignmentModal'

// The real API client (the shared test setup mocks it), so its token
// refresh runs against the mocked fetch below.
jest.unmock('@/lib/api')
jest.unmock('@/lib/api/base')

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) =>
      ({
        'tasks.assignment.assign': 'Assign Tasks',
        'tasks.assignment.assigned': 'Tasks assigned successfully',
        'tasks.assignment.assignFailed': 'Failed to assign tasks',
      })[key] ?? key,
    locale: 'en',
  }),
}))

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    headers: new Headers({ 'content-type': 'application/json' }),
    text: () => Promise.resolve(JSON.stringify(body)),
    json: () => Promise.resolve(body),
  }
}

describe('TaskAssignmentModal with an expired access token', () => {
  const fetchMock = jest.fn()

  beforeEach(() => {
    mockAddToast.mockReset()
    fetchMock.mockReset()
    ;(global as any).fetch = fetchMock
  })

  it('refreshes the token and assigns the tasks', async () => {
    let assignCalls = 0
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/auth/refresh')) {
        return Promise.resolve(jsonResponse(200, {}))
      }
      if (url.endsWith('/projects/project-123/tasks/assign')) {
        assignCalls += 1
        return Promise.resolve(
          assignCalls === 1
            ? jsonResponse(401, { detail: 'Token expired' })
            : jsonResponse(200, {
                assignments_created: 2,
                assignments_updated: 0,
                assignments_skipped: 0,
                message: 'Created 2 new assignments',
              }),
        )
      }
      return Promise.resolve(jsonResponse(404, {}))
    })
    const onAssignmentComplete = jest.fn().mockResolvedValue(undefined)
    const onClose = jest.fn()

    const user = userEvent.setup()
    render(
      <TaskAssignmentModal
        isOpen
        onClose={onClose}
        projectId="project-123"
        selectedTaskIds={['task-1', 'task-2']}
        projectMembers={[
          {
            id: 'member-1',
            user_id: 'user-1',
            name: 'John Doe',
            email: 'john@example.com',
            role: 'annotator',
          },
        ]}
        onAssignmentComplete={onAssignmentComplete}
      />,
    )

    await user.click(screen.getAllByRole('checkbox')[0])
    await user.click(screen.getByRole('button', { name: /Assign Tasks/i }))

    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith(
        'Tasks assigned successfully',
        'success',
      )
    })
    expect(assignCalls).toBe(2)
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith('/auth/refresh'),
      ),
    ).toBe(true)
    expect(mockAddToast).not.toHaveBeenCalledWith(
      'Failed to assign tasks',
      'error',
    )
    expect(onAssignmentComplete).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })
})
