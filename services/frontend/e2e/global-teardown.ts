import { spawn } from 'child_process'
import { existsSync } from 'fs'
import * as path from 'path'

// Playwright runs from services/frontend, and the compose files live in the
// repository root's infra directory. The old '../infra' pointed at
// services/infra, which does not exist, so every teardown failed with
// "spawn sh ENOENT" before it could run anything.
const infraDir = path.resolve(process.cwd(), '../../infra')

/**
 * Execute a command with timeout protection to prevent hangs
 * Uses spawn instead of execSync to allow forced termination
 */
function executeWithTimeout(
  cmd: string,
  cwd: string,
  timeout: number = 60000,
): Promise<{ success: boolean; timedOut: boolean }> {
  return new Promise((resolve) => {
    const proc = spawn('sh', ['-c', cmd], { cwd, stdio: 'inherit' })
    let timedOut = false

    const timer = setTimeout(() => {
      timedOut = true
      console.warn(
        `Teardown timed out after ${timeout / 1000}s, force killing...`,
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

  // Stopping the stack is opt-in. The local workflow starts it once
  // (make test-start), runs make test-e2e against it many times and stops it
  // explicitly (make test-stop). Stopping it after every run would force a
  // full restart and re-seed each time. Set E2E_CLEANUP=true to stop it here.
  const shouldCleanup = process.env.E2E_CLEANUP === 'true'
  const isIsolatedE2E = process.env.E2E_ISOLATED === 'true'

  if (isIsolatedE2E && shouldCleanup) {
    if (!existsSync(path.join(infraDir, 'docker-compose.test.yml'))) {
      console.warn(
        `No docker-compose.test.yml under ${infraDir}, nothing was stopped`,
      )
    } else {
      console.log('Stopping E2E Docker containers (E2E_CLEANUP=true)...')

      // Use 60 second timeout - if Docker is stuck, force kill and continue
      const result = await executeWithTimeout(
        'docker compose -f docker-compose.test.yml down',
        infraDir,
        60000,
      )

      if (result.success) {
        console.log('E2E Docker environment stopped')
      } else if (result.timedOut) {
        console.warn('Teardown timed out - containers may still be running')
        console.log('Stop them with: make test-stop')
      } else {
        console.warn('Failed to stop E2E Docker containers')
        console.log('Stop them with: make test-stop')
      }
    }
  } else if (isIsolatedE2E) {
    console.log(
      'E2E containers left running. make test-stop stops them, or set E2E_CLEANUP=true to stop them after a run.',
    )
  }

  console.log('E2E test teardown complete')
}

export default globalTeardown
