import { NextRequest, NextResponse } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

export async function POST(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''
    const authorization = request.headers.get('authorization') || ''
    const body = await request.json()

    // Forward the request to the backend with cookies
    const backendResponse = await fetch(
      `${apiBaseUrl}/api/auth/change-password`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Cookie: cookies, // Forward cookies for authentication
          Authorization: authorization, // Forward authorization header
        },
        body: JSON.stringify(body),
      }
    )

    // Get the response data
    if (!backendResponse.ok) {
      const errorData = await backendResponse.text()
      return NextResponse.json(
        { error: errorData || 'Password change failed' },
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('❌ Change password proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
