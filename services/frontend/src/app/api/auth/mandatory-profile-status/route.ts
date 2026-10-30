import { getInternalApiUrl } from '@/lib/utils/apiUrl'
import { proxyAuthHeaders } from '@/lib/utils/proxyAuthHeaders'
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)

    const backendResponse = await fetch(
      `${apiBaseUrl}/api/auth/mandatory-profile-status`,
      {
        method: 'GET',
        headers: {
          ...proxyAuthHeaders(request),
        },
      },
    )

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
    console.error('Mandatory profile status proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}
