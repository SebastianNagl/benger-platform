import { NextRequest, NextResponse } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

// Dedicated auth-write proxy for the Vertretbar plan-choice greeting flag
// (extended one-time modal). The catch-all /api/[...path] handler rejects
// `auth/*` writes with 400 "Use dedicated auth handler" because they carry
// session cookies, so this generic cookie/authorization forwarder is required
// for the client's POST to reach the backend. No proprietary logic — mirrors
// the confirm-profile proxy.
export async function POST(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''
    const authorization = request.headers.get('authorization') || ''

    const backendResponse = await fetch(
      `${apiBaseUrl}/api/auth/me/vertretbar-onboarding`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Cookie: cookies,
          Authorization: authorization,
        },
      }
    )

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
    console.error('Vertretbar onboarding proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
