import { getInternalApiUrl } from '@/lib/utils/apiUrl'
import { proxyAuthHeaders } from '@/lib/utils/proxyAuthHeaders'
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)

    // Forward the session cookie, and an access key when one was sent
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/me`, {
      method: 'GET',
      headers: proxyAuthHeaders(request),
    })

    // Get the response data
    if (!backendResponse.ok) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: backendResponse.status },
      )
    }

    const data = await backendResponse.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('❌ Auth check proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}
