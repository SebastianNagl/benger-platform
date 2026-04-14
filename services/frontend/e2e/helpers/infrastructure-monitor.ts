/**
 * Infrastructure monitoring utilities for E2E tests
 * Provides resource usage logging and health diagnostics
 */
import { execSync } from 'child_process'

const E2E_CONTAINERS = [
  'api-e2e',
  'worker-e2e',
  'db-e2e',
  'redis-e2e',
  'frontend-e2e',
  'traefik-e2e',
  'scheduler-e2e',
]

interface ContainerStats {
  name: string
  memUsage: string
  cpuPercent: string
  running: boolean
}

interface InfrastructureHealth {
  containers: ContainerStats[]
  allRunning: boolean
  timestamp: string
}

/**
 * Get current resource usage for E2E containers
 * Useful for diagnosing memory/CPU exhaustion during test runs
 */
export function getContainerStats(): ContainerStats[] {
  const stats: ContainerStats[] = []

  for (const container of E2E_CONTAINERS) {
    try {
      const output = execSync(
        `docker stats infra-${container}-1 --no-stream --format "{{.MemUsage}} {{.CPUPerc}}"`,
        { encoding: 'utf8', timeout: 5000 }
      ).trim()

      const parts = output.split(' ')
      stats.push({
        name: container,
        memUsage: parts[0] || 'N/A',
        cpuPercent: parts[parts.length - 1] || 'N/A',
        running: true,
      })
    } catch {
      stats.push({
        name: container,
        memUsage: 'N/A',
        cpuPercent: 'N/A',
        running: false,
      })
    }
  }

  return stats
}

/**
 * Log infrastructure health to console
 * Call this periodically during test runs to monitor resource usage
 */
export function logInfrastructureHealth(): InfrastructureHealth {
  const stats = getContainerStats()
  const allRunning = stats.every((s) => s.running)
  const timestamp = new Date().toISOString()

  console.log(`\n=== Infrastructure Health (${timestamp}) ===`)

  for (const stat of stats) {
    if (stat.running) {
      console.log(`  ${stat.name}: ${stat.memUsage} | CPU: ${stat.cpuPercent}`)
    } else {
      console.log(`  ${stat.name}: NOT RUNNING`)
    }
  }

  if (!allRunning) {
    const notRunning = stats.filter((s) => !s.running).map((s) => s.name)
    console.warn(`WARNING: Containers not running: ${notRunning.join(', ')}`)
  }

  console.log('==========================================\n')

  return { containers: stats, allRunning, timestamp }
}

/**
 * Check if all E2E containers are running
 */
export function areAllContainersRunning(): boolean {
  const stats = getContainerStats()
  return stats.every((s) => s.running)
}

/**
 * Get containers that are not running
 */
export function getStoppedContainers(): string[] {
  const stats = getContainerStats()
  return stats.filter((s) => !s.running).map((s) => s.name)
}

/**
 * Check database connection count
 * High connection counts can indicate connection leaks
 */
export async function checkDatabaseConnections(
  apiUrl: string
): Promise<number> {
  try {
    const response = await fetch(`${apiUrl}/api/health/detailed`, {
      timeout: 5000,
    } as RequestInit)
    if (!response.ok) return -1

    const health = await response.json()
    return health.database_connections || -1
  } catch {
    return -1
  }
}

/**
 * Monitor infrastructure and return warning if resources are strained
 * Returns null if healthy, or a warning message if issues detected
 */
export function checkResourceHealth(): string | null {
  const stats = getContainerStats()
  const warnings: string[] = []

  for (const stat of stats) {
    if (!stat.running) {
      warnings.push(`${stat.name} is not running`)
      continue
    }

    // Check for high memory usage (>80%)
    const memMatch = stat.memUsage.match(/(\d+\.?\d*)([MGG]iB)/)
    const limitMatch = stat.memUsage.match(/\/\s*(\d+\.?\d*)([MGG]iB)/)

    if (memMatch && limitMatch) {
      const used = parseFloat(memMatch[1])
      const limit = parseFloat(limitMatch[1])
      const usedUnit = memMatch[2]
      const limitUnit = limitMatch[2]

      // Normalize to same unit
      let usedMB = used
      let limitMB = limit
      if (usedUnit === 'GiB') usedMB = used * 1024
      if (limitUnit === 'GiB') limitMB = limit * 1024

      const percentUsed = (usedMB / limitMB) * 100
      if (percentUsed > 80) {
        warnings.push(`${stat.name} memory at ${percentUsed.toFixed(0)}%`)
      }
    }

    // Check for high CPU usage (>90%)
    const cpuMatch = stat.cpuPercent.match(/(\d+\.?\d*)%/)
    if (cpuMatch) {
      const cpu = parseFloat(cpuMatch[1])
      if (cpu > 90) {
        warnings.push(`${stat.name} CPU at ${cpu.toFixed(0)}%`)
      }
    }
  }

  return warnings.length > 0 ? warnings.join('; ') : null
}
