import { NextRequest } from 'next/server'
import { getInternalApiUrl } from '@/lib/utils/apiUrl'

// Configure Next.js route segment config for SSE
export const dynamic = 'force-dynamic'
export const maxDuration = 600 // 10 minutes max for evaluation streaming

// SSE proxy endpoint for evaluation status streaming
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ evaluationId: string }> }
) {
  const { evaluationId } = await params

  const apiBaseUrl = getInternalApiUrl(request)

  const cookies = request.headers.get('cookie') || ''

  try {
    // Proxy the SSE request to the backend API
    const response = await fetch(
      `${apiBaseUrl}/api/evaluations/stream/${evaluationId}`,
      {
        headers: {
          Cookie: cookies,
          Accept: 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
      }
    )

    if (!response.ok) {
      return new Response(
        JSON.stringify({ error: 'Failed to connect to evaluation stream' }),
        { status: response.status }
      )
    }

    // Return the SSE stream
    return new Response(response.body, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    })
  } catch (error) {
    console.error('Evaluation stream proxy error:', error)
    return new Response(
      JSON.stringify({ error: 'Failed to connect to evaluation stream' }),
      { status: 500 }
    )
  }
}
