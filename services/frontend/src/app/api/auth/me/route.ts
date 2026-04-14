import { NextRequest, NextResponse } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

export async function GET(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''

    // Forward the request to the backend with cookies
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/me`, {
      method: 'GET',
      headers: {
        Cookie: cookies, // Forward cookies for authentication
      },
    })

    // Get the response data
    if (!backendResponse.ok) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('❌ Auth check proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
