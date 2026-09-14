import { NextRequest, NextResponse } from 'next/server'

/**
 * Health check endpoint for container monitoring
 * Returns the health status and runtime information of the Next.js server
 */
export async function GET(request: NextRequest) {
  try {
    // Basic health check - verify application is running
    const health: Record<string, unknown> = {
      status: 'healthy',
      timestamp: new Date().toISOString(),
      environment: process.env.NODE_ENV || 'development',
      memory: {
        used: Math.round(process.memoryUsage().heapUsed / 1024 / 1024),
        total: Math.round(process.memoryUsage().heapTotal / 1024 / 1024),
        limit:
          parseInt(
            process.env.NODE_OPTIONS?.match(
              /--max-old-space-size=(\d+)/,
            )?.[1] || '0',
          ) || 2048,
        unit: 'MB',
      },
      uptime: Math.round(process.uptime()),
      version: process.version,
    }

    // Check memory usage - warn if over 80%
    const mem = health.memory as { used: number; limit: number }
    const memoryUsagePercent = (mem.used / mem.limit) * 100
    if (memoryUsagePercent > 80) {
      health.status = 'warning'
      health.warning = `High memory usage: ${memoryUsagePercent.toFixed(1)}%`
    }

    // Backend, database and Redis status live on the API's own /health.
    // This route only reports on the Next.js server. A backend check here was
    // keyed on API_BASE_URL, which no deployment sets, so it never ran, and
    // probing the API from a liveness check would tie the frontend's health
    // to the API's.

    // A memory "warning" (high-but-not-OOM heap) is surfaced in the body for
    // observability but does NOT fail the probe: the server is still serving.
    // Returning 503 here used to fail both the container healthcheck and the
    // Traefik load-balancer healthcheck, which dropped this backend from the
    // pool ("no available server") during normal Next.js dev use — where the
    // dev server's heap legitimately runs high over a long session. Only a
    // genuine failure (the catch block below) returns 503.
    return NextResponse.json(health, { status: 200 })
  } catch (error) {
    // If we can't even run this check, the app is unhealthy
    return NextResponse.json(
      {
        status: 'unhealthy',
        error: error instanceof Error ? error.message : 'Unknown error',
        timestamp: new Date().toISOString(),
      },
      { status: 503 },
    )
  }
}
