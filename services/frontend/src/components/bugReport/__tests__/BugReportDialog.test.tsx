/**
 * @jest-environment jsdom
 *
 * The "Report a problem" dialog: required fields, the contact address only
 * without a session, screenshots by file or paste (type and size checked),
 * the preview of what is attached, the multipart request and the answers of
 * the API (sent, rate limited, network error).
 */
import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'

import { BugReportDialog, MAX_SCREENSHOT_BYTES } from '../BugReportDialog'

// The real API client (the shared test setup mocks it), so its requests and
// token refresh run against the mocked fetch below.
jest.unmock('@/lib/api')
jest.unmock('@/lib/api/base')

let mockAuth: { user: any; organizations: any[] } | null = null
jest.mock('@/contexts/AuthContext', () => ({
  useOptionalAuth: () => mockAuth,
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))
jest.mock('@/lib/featureFlags', () => ({
  getFeatureFlagMap: () => ({ bug_reports: true, other: false }),
}))
jest.mock('@/lib/extensions/active', () => ({
  getActiveExtensions: () => ['extended'],
}))

const fetchMock = jest.fn()

function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: '',
    headers: new Headers({ 'content-type': 'application/json', ...headers }),
    text: async () => JSON.stringify(body),
    json: async () => body,
  }
}

function renderDialog(
  props: Partial<React.ComponentProps<typeof BugReportDialog>> = {},
) {
  const onClose = jest.fn()
  render(
    <BugReportDialog
      open
      onClose={onClose}
      source="footer"
      extraContext={{ routeParams: { id: 'p-1' }, uiMode: 'expert' }}
      {...props}
    />,
  )
  return { onClose }
}

function fill(title = 'Save fails', description = 'Nothing happens') {
  fireEvent.change(screen.getByLabelText('bugReport.fields.title'), {
    target: { value: title },
  })
  fireEvent.change(screen.getByLabelText('bugReport.fields.description'), {
    target: { value: description },
  })
}

const png = () =>
  new File([new Uint8Array([137, 80, 78, 71])], 'shot.png', {
    type: 'image/png',
  })

beforeEach(() => {
  mockAuth = null
  fetchMock.mockReset()
  ;(global as any).fetch = fetchMock
  ;(URL as any).createObjectURL = jest.fn(() => 'blob:preview')
  ;(URL as any).revokeObjectURL = jest.fn()
})

describe('BugReportDialog', () => {
  it('asks for a contact address only without a session', () => {
    renderDialog()
    expect(
      screen.getByLabelText('bugReport.fields.contactEmail'),
    ).toBeInTheDocument()
  })

  it('hides the contact address for a signed-in user', () => {
    mockAuth = { user: { id: 'u1' }, organizations: [{ role: 'ORG_ADMIN' }] }
    renderDialog()
    expect(screen.queryByLabelText('bugReport.fields.contactEmail')).toBeNull()
  })

  it('shows what is attached before sending', () => {
    mockAuth = { user: { id: 'u1' }, organizations: [{ role: 'CONTRIBUTOR' }] }
    renderDialog()
    const preview = JSON.parse(
      screen.getByTestId('bug-report-context').textContent!,
    )
    expect(preview).toMatchObject({
      source: 'footer',
      route_params: { id: 'p-1' },
      ui_mode: 'expert',
      feature_flags: ['bug_reports'],
      extensions: ['extended'],
      org_roles: ['CONTRIBUTOR'],
      locale: 'en',
    })
  })

  it('requires a summary and a description', async () => {
    renderDialog()
    fireEvent.click(screen.getByText('bugReport.send'))
    expect(await screen.findByTestId('bug-report-error')).toHaveTextContent(
      'bugReport.errors.titleRequired',
    )
    fireEvent.change(screen.getByLabelText('bugReport.fields.title'), {
      target: { value: 'x' },
    })
    fireEvent.click(screen.getByText('bugReport.send'))
    expect(await screen.findByTestId('bug-report-error')).toHaveTextContent(
      'bugReport.errors.descriptionRequired',
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sends the report as multipart with context and screenshot', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(201, { id: 'r1', status: 'pending' }),
    )
    renderDialog()
    fill()
    fireEvent.change(screen.getByLabelText('bugReport.fields.expected'), {
      target: { value: 'It saves' },
    })
    fireEvent.change(screen.getByLabelText('bugReport.fields.contactEmail'), {
      target: { value: 'me@example.org' },
    })
    fireEvent.change(screen.getByTestId('bug-report-file'), {
      target: { files: [png()] },
    })
    expect(screen.getByAltText('bugReport.screenshotPreview')).toHaveAttribute(
      'src',
      'blob:preview',
    )
    await act(async () => {
      fireEvent.click(screen.getByText('bugReport.send'))
    })
    expect(await screen.findByTestId('bug-report-sent')).toBeInTheDocument()
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/bug-reports')
    expect(init).toMatchObject({ method: 'POST', credentials: 'include' })
    const form = init.body as FormData
    expect(form.get('title')).toBe('Save fails')
    expect(form.get('description')).toBe('Nothing happens')
    expect(form.get('expected')).toBe('It saves')
    expect(form.get('contact_email')).toBe('me@example.org')
    expect(JSON.parse(form.get('context') as string).source).toBe('footer')
    expect((form.get('screenshot') as File).name).toBe('shot.png')
  })

  it('refreshes an expired session first, so a signed-in report is not filed anonymously', async () => {
    // The report route takes anonymous reports too, so an expired access
    // token is no 401 there: the report would be stored without its author.
    mockAuth = { user: { id: 'u-1', name: 'Ann' }, organizations: [] }
    let sessionFresh = false
    fetchMock.mockImplementation((url: string) => {
      if (url.endsWith('/auth/me')) {
        return Promise.resolve(
          sessionFresh
            ? jsonResponse(200, { id: 'u-1' })
            : jsonResponse(401, { detail: 'Token expired' }),
        )
      }
      if (url.endsWith('/auth/refresh')) {
        sessionFresh = true
        return Promise.resolve(jsonResponse(200, {}))
      }
      if (url.endsWith('/bug-reports')) {
        return Promise.resolve(
          jsonResponse(201, {
            id: 'r1',
            status: sessionFresh ? 'pending' : 'anonymous',
          }),
        )
      }
      return Promise.resolve(jsonResponse(404, {}))
    })
    renderDialog()
    fill()
    await act(async () => {
      fireEvent.click(screen.getByText('bugReport.send'))
    })
    expect(await screen.findByTestId('bug-report-sent')).toBeInTheDocument()
    const urls = fetchMock.mock.calls.map(([url]) => String(url))
    const refreshAt = urls.findIndex((u) => u.endsWith('/auth/refresh'))
    const reportAt = urls.findIndex((u) => u.endsWith('/bug-reports'))
    expect(refreshAt).toBeGreaterThanOrEqual(0)
    expect(reportAt).toBeGreaterThan(refreshAt)
  })

  it('takes a pasted screenshot and refuses other types and huge files', () => {
    renderDialog()
    const form = screen.getByTestId('bug-report-form')
    fireEvent.paste(form, {
      clipboardData: {
        items: [{ type: 'image/png', getAsFile: () => png() }],
      },
    })
    expect(
      screen.getByAltText('bugReport.screenshotPreview'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByText('bugReport.removeScreenshot'))
    fireEvent.change(screen.getByTestId('bug-report-file'), {
      target: {
        files: [new File(['<svg/>'], 'x.svg', { type: 'image/svg+xml' })],
      },
    })
    expect(screen.getByTestId('bug-report-error')).toHaveTextContent(
      'bugReport.errors.screenshotType',
    )
    const huge = png()
    Object.defineProperty(huge, 'size', { value: MAX_SCREENSHOT_BYTES + 1 })
    fireEvent.change(screen.getByTestId('bug-report-file'), {
      target: { files: [huge] },
    })
    expect(screen.getByTestId('bug-report-error')).toHaveTextContent(
      'bugReport.errors.screenshotTooLarge',
    )
    expect(screen.queryByAltText('bugReport.screenshotPreview')).toBeNull()
  })

  it('explains a refusal of the API', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        429,
        { detail: { code: 'rate_limited' } },
        { 'retry-after': '3600' },
      ),
    )
    renderDialog()
    fill()
    await act(async () => {
      fireEvent.click(screen.getByText('bugReport.send'))
    })
    expect(await screen.findByTestId('bug-report-error')).toHaveTextContent(
      'bugReport.errors.rateLimited',
    )
    fetchMock.mockResolvedValue(jsonResponse(500, {}))
    await act(async () => {
      fireEvent.click(screen.getByText('bugReport.send'))
    })
    expect(screen.getByTestId('bug-report-error')).toHaveTextContent(
      'bugReport.errors.generic',
    )
    fetchMock.mockRejectedValue(new TypeError('offline'))
    await act(async () => {
      fireEvent.click(screen.getByText('bugReport.send'))
    })
    expect(screen.getByTestId('bug-report-error')).toHaveTextContent(
      'bugReport.errors.network',
    )
  })

  it('closes on cancel', async () => {
    const { onClose } = renderDialog()
    fireEvent.click(screen.getByText('common.cancel'))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })
})
