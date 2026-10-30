import { getInternalApiUrl } from '@/lib/utils/apiUrl'
import { proxyAuthHeaders } from '@/lib/utils/proxyAuthHeaders'
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)

    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/me/contexts`, {
      method: 'GET',
      headers: proxyAuthHeaders(request),
    })

    if (!backendResponse.ok) {
      return NextResponse.json(
        { error: 'Unauthorized' },
        { status: backendResponse.status },
      )
    }

    const data = await backendResponse.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error('Auth me/contexts proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}
