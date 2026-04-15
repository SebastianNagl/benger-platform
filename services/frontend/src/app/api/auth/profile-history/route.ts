import { NextRequest, NextResponse } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

export async function GET(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const cookies = request.headers.get('cookie') || ''
    const authorization = request.headers.get('authorization') || ''
    const { searchParams } = new URL(request.url)
    const queryString = searchParams.toString()
    const url = `${apiBaseUrl}/api/auth/profile-history${queryString ? `?${queryString}` : ''}`

    const backendResponse = await fetch(url, {
      method: 'GET',
      headers: {
        Cookie: cookies,
        Authorization: authorization,
      },
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
    console.error('Profile history proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
