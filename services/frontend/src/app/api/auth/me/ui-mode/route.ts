import { NextRequest, NextResponse } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

// Dedicated auth-write proxy for the student/expert view-mode preference
// (issue #35). This route was MISSING when the endpoint shipped: the catch-all
// /api/[...path] handler rejects `auth/*` writes with 400 "Use dedicated auth
// handler", so apiClient.setUiMode() could never reach the backend from the
// browser — masked because the closed-beta lock keeps the switch surface
// unreachable and useViewModeSwitch swallows persist failures (keeping the
// optimistic local value). Same generic forwarder as the exam-layout proxy.
export async function PUT(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''
    const authorization = request.headers.get('authorization') || ''
    const body = await request.json()

    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/me/ui-mode`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Cookie: cookies,
        Authorization: authorization,
      },
      body: JSON.stringify(body),
    })

    if (!backendResponse.ok) {
      const errorData = await backendResponse.text()
      return NextResponse.json(
        { error: errorData || 'Request failed' },
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('UI mode proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
