import { spawn } from 'child_process'
import * as path from 'path'

// Use process.cwd() since we're running from frontend directory
const infraDir = path.resolve(process.cwd(), '../infra')

/**
 * Execute a command with timeout protection to prevent hangs
 * Uses spawn instead of execSync to allow forced termination
 */
function executeWithTimeout(
  cmd: string,
  cwd: string,
  timeout: number = 60000
): Promise<{ success: boolean; timedOut: boolean }> {
  return new Promise((resolve) => {
    const proc = spawn('sh', ['-c', cmd], { cwd, stdio: 'inherit' })
    let timedOut = false

    const timer = setTimeout(() => {
      timedOut = true
      console.warn(
        `Teardown timed out after ${timeout / 1000}s, force killing...`
      )
      proc.kill('SIGKILL')
    }, timeout)

    proc.on('close', (code) => {
      clearTimeout(timer)
      resolve({ success: code === 0, timedOut })
    })

    proc.on('error', (err) => {
      clearTimeout(timer)
      console.error('Process error:', err.message)
      resolve({ success: false, timedOut: false })
    })
  })
}

async function globalTeardown() {
  console.log('Running E2E test global teardown...')

  // Check if we should clean up the E2E Docker environment
  // Set E2E_CLEANUP=false to keep containers running for debugging
  const shouldCleanup = process.env.E2E_CLEANUP !== 'false'
  const isIsolatedE2E = process.env.E2E_ISOLATED === 'true'

  if (shouldCleanup && isIsolatedE2E) {
    console.log('Stopping E2E Docker containers...')

    // Use 60 second timeout - if Docker is stuck, force kill and continue
    const result = await executeWithTimeout(
      'docker-compose -f docker-compose.test.yml down',
      infraDir,
      60000
    )

    if (result.success) {
      console.log('E2E Docker environment stopped and cleaned up')
    } else if (result.timedOut) {
      console.warn('Teardown timed out - containers may still be running')
      console.log(
        'Clean up manually with: cd infra && docker-compose -f docker-compose.test.yml down -t 0'
      )
    } else {
      console.warn('Failed to stop E2E Docker containers')
      console.log(
        'Clean up manually with: cd infra && docker-compose -f docker-compose.test.yml down'
      )
    }
  } else if (isIsolatedE2E && !shouldCleanup) {
    console.log('E2E containers left running for debugging (E2E_CLEANUP=false)')
    console.log(
      'Clean up manually with: cd infra && docker-compose -f docker-compose.test.yml down'
    )
  }

  console.log('E2E test teardown complete')
}

export default globalTeardown
