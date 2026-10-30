import { getInternalApiUrl } from '@/lib/utils/apiUrl'
import { proxyAuthHeaders } from '@/lib/utils/proxyAuthHeaders'
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const { searchParams } = new URL(request.url)
    const queryString = searchParams.toString()
    const url = `${apiBaseUrl}/api/auth/profile-history${queryString ? `?${queryString}` : ''}`

    const backendResponse = await fetch(url, {
      method: 'GET',
      headers: {
        ...proxyAuthHeaders(request),
      },
    })

    if (!backendResponse.ok) {
      const errorData = await backendResponse.text()
      return NextResponse.json(
        { error: errorData || 'Request failed' },
        { status: backendResponse.status },
      )
    }

    const data = await backendResponse.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Profile history proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}
