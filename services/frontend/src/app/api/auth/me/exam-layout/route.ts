import { NextRequest, NextResponse } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

// Dedicated auth-write proxy for the exam interface layout preference
// (extended profile section). The catch-all /api/[...path] handler rejects
// `auth/*` writes with 400 "Use dedicated auth handler" because they carry
// session cookies, so this generic cookie/authorization/body forwarder is
// required for the client's PUT to reach the backend. No proprietary logic —
// mirrors the vertretbar-onboarding proxy plus the profile proxy's body
// forwarding.
export async function PUT(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''
    const authorization = request.headers.get('authorization') || ''
    const body = await request.json()

    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/me/exam-layout`, {
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
    console.error('Exam layout proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
