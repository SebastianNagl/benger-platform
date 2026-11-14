import {
  forwardedForHeaders,
  getExternalHost,
  getInternalApiUrl,
} from '@/lib/utils/apiUrl'
import { readJsonBody } from '@/lib/utils/jsonBody'
import { proxyAuthHeaders } from '@/lib/utils/proxyAuthHeaders'
import { NextRequest, NextResponse } from 'next/server'

export async function GET(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)

    // Forward the request to the backend with cookies
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/profile`, {
      method: 'GET',
      headers: {
        ...proxyAuthHeaders(request),
      },
    })

    // Get the response data
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
    console.error('❌ Profile fetch proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}

export async function PUT(request: NextRequest) {
  try {
    const apiBaseUrl = getInternalApiUrl(request)
    const parsed = await readJsonBody(request)
    if (!parsed.ok) return parsed.response
    const body = parsed.body

    // Forward the request to the backend with cookies. A changed email
    // address gets a confirmation mail: the external host brands it and its
    // link (Vertretbar on vertretbar.net), as for the verification mail, and
    // the client address feeds the API's per-IP limits.
    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/profile`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'x-forwarded-host': getExternalHost(request),
        ...forwardedForHeaders(request),
        ...proxyAuthHeaders(request),
      },
      body: JSON.stringify(body),
    })

    // Get the response data
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
    console.error('❌ Profile update proxy error:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 },
    )
  }
}
