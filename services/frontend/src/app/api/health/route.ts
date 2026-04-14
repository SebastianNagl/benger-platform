import { NextRequest, NextResponse } from 'next/server'

/**
 * Health check endpoint for container monitoring
 * Returns basic health status, runtime information, and backend connectivity
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
              /--max-old-space-size=(\d+)/
            )?.[1] || '0'
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

    // Check backend API connectivity when API_BASE_URL is configured
    const apiBaseUrl = process.env.API_BASE_URL
    if (apiBaseUrl) {
      try {
        const backendRes = await fetch(`${apiBaseUrl}/health`, {
          signal: AbortSignal.timeout(3000),
        })
        if (backendRes.ok) {
          health.backend = 'ok'
          const backendData = await backendRes.json().catch(() => ({}))
          health.database = backendData.database || 'unknown'
          health.redis = backendData.redis || 'unknown'
        } else {
          health.backend = 'error'
        }
      } catch {
        health.backend = 'unreachable'
      }
    }

    // Return 200 OK for healthy, 503 for warnings
    const status = health.status === 'healthy' ? 200 : 503

    return NextResponse.json(health, { status })
  } catch (error) {
    // If we can't even run this check, the app is unhealthy
    return NextResponse.json(
      {
        status: 'unhealthy',
        error: error instanceof Error ? error.message : 'Unknown error',
        timestamp: new Date().toISOString(),
      },
      { status: 503 }
    )
  }
}
