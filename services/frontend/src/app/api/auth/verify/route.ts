import { NextRequest, NextResponse } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

export async function GET(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''
    const authorization = request.headers.get('authorization') || ''

    // Forward the request to the backend with cookies
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/verify`, {
      method: 'GET',
      headers: {
        Cookie: cookies, // Forward cookies for authentication
        Authorization: authorization, // Forward authorization header
      },
    })

    // Get the response data
    if (!backendResponse.ok) {
      const errorData = await backendResponse.text()
      return NextResponse.json(
        { error: errorData || 'Verification failed' },
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('❌ Auth verify proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
