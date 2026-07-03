import { NextRequest, NextResponse } from 'next/server'
import { logger } from '@/lib/utils/logger'
import { getInternalApiUrl, getExternalHost } from '@/lib/utils/apiUrl'

// Dedicated handler: the generic /api/[...path] proxy blocks /api/auth/* and
// forces auth calls through dedicated routes. Forward the resolved external host
// as x-forwarded-host so the backend brands the verification email host-aware
// (Vertretbar on vertretbar.net) and builds the link on the right host.
export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const apiBaseUrl = getInternalApiUrl(request)

    logger.debug('📮 Resend-verification →', `${apiBaseUrl}/api/auth/resend-verification`)

    const backendResponse = await fetch(`${apiBaseUrl}/api/auth/resend-verification`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-forwarded-host': getExternalHost(request),
      },
      body: JSON.stringify(body),
    })

    const data = await backendResponse.json()
    return NextResponse.json(data, { status: backendResponse.status })
  } catch (error) {
    console.error('❌ Resend-verification proxy error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
