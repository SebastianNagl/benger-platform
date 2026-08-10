/**
 * Tests for the AuthClient preference endpoints: setExamLayout (exam interface
 * layout) and setUiMode (student/expert shell). Asserts the exact request
 * path/method/body — these must match the dedicated Next proxy routes (the
 * catch-all rejects auth/* writes, so a drifted path fails only in the
 * browser).
 */

import { AuthClient } from '../auth'
import type { ExamLayoutPrefs } from '../types'

const mockRequest = jest.fn()

jest.mock('../base', () => ({
  BaseApiClient: class MockBaseApiClient {
    invalidateCache(_pattern: string | RegExp) {}
    protected async request<T>(url: string, options?: RequestInit): Promise<T> {
      return mockRequest(url, options) as T
    }
  },
}))

describe('AuthClient exam layout + ui mode preferences', () => {
  beforeEach(() => {
    mockRequest.mockReset()
    mockRequest.mockResolvedValue({ id: 'u1' })
  })

  it('setExamLayout PUTs the complete object to /auth/me/exam-layout', async () => {
    const prefs: ExamLayoutPrefs = {
      mode: 'modern',
      case_position: 'left',
      notes_position: 'right',
      outline_position: 'none',
    }
    const client = new AuthClient()

    await client.setExamLayout(prefs)

    expect(mockRequest).toHaveBeenCalledWith('/auth/me/exam-layout', {
      method: 'PUT',
      body: JSON.stringify({ exam_layout_prefs: prefs }),
    })
  })

  it('setExamLayout(null) clears the stored preference', async () => {
    const client = new AuthClient()

    await client.setExamLayout(null)

    expect(mockRequest).toHaveBeenCalledWith('/auth/me/exam-layout', {
      method: 'PUT',
      body: JSON.stringify({ exam_layout_prefs: null }),
    })
  })

  it('setUiMode PUTs the mode to /auth/me/ui-mode', async () => {
    const client = new AuthClient()

    await client.setUiMode('student')

    expect(mockRequest).toHaveBeenCalledWith('/auth/me/ui-mode', {
      method: 'PUT',
      body: JSON.stringify({ preferred_ui_mode: 'student' }),
    })
  })
})
