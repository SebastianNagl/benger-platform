import { NextRequest, NextResponse } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

export async function GET(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''

    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/me/contexts`, {
      method: 'GET',
      headers: {
        Cookie: cookies,
      },
    })

    if (!backendResponse.ok) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: backendResponse.status }
      )
    }

    const data = await backendResponse.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Auth me/contexts proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
