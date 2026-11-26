/**
 * @jest-environment node
 *
 * Runs scripts/sync-dev-node-modules.sh (the dev container's lockfile sync)
 * as the entrypoint does, in a throwaway app directory with a stub `npm` on
 * PATH. The expected behaviour comes from the script's contract: reinstall
 * only when node_modules/.lockfile-sha256 differs from the sha256 of
 * package-lock.json, keep packages that are mounted inside node_modules, and
 * leave neither staging leftovers nor a touched node_modules behind when the
 * install fails.
 */
import { spawnSync } from 'child_process'
import { createHash } from 'crypto'
import fs from 'fs'
import os from 'os'
import path from 'path'

const SCRIPT = path.resolve(
  __dirname,
  '../../../scripts/sync-dev-node-modules.sh',
)

// Stub npm: records each call, then either fails partway through an install
// (leaving a partial tree in its working directory, as a real npm ci does)
// or writes a fresh node_modules with a known package version.
const STUB_NPM = `#!/bin/sh
echo "$PWD $*" >> "$NPM_CALLS"
mkdir -p node_modules/partial
echo half > node_modules/partial/file
if [ "$STUB_NPM_MODE" = fail ]; then
  echo "npm error network unreachable" >&2
  exit 1
fi
rm -rf node_modules
mkdir -p node_modules/next node_modules/.bin
echo '{"name":"next","version":"16.4.6"}' > node_modules/next/package.json
echo fresh > node_modules/.bin/next
`

const LOCKFILE = '{"name":"app","lockfileVersion":3,"packages":{}}\n'
const lockHash = createHash('sha256').update(LOCKFILE).digest('hex')

let root: string
let app: string
let tmp: string
let bin: string
let calls: string
let mountinfo: string

function run(mode: 'fail' | 'succeed') {
  return spawnSync('sh', [SCRIPT], {
    cwd: app,
    encoding: 'utf8',
    env: {
      PATH: `${bin}:${process.env.PATH}`,
      TMPDIR: tmp,
      MOUNTINFO: mountinfo,
      NPM_CALLS: calls,
      STUB_NPM_MODE: mode,
    },
  })
}

function npmCalls(): string[] {
  return fs.existsSync(calls)
    ? fs.readFileSync(calls, 'utf8').trim().split('\n').filter(Boolean)
    : []
}

function write(rel: string, content: string) {
  const file = path.join(app, rel)
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, content)
}

function read(rel: string) {
  return fs.readFileSync(path.join(app, rel), 'utf8')
}

beforeEach(() => {
  root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'sync-nm-')))
  app = path.join(root, 'app')
  tmp = path.join(root, 'tmp')
  bin = path.join(root, 'bin')
  calls = path.join(root, 'npm-calls.log')
  mountinfo = path.join(root, 'mountinfo')
  fs.mkdirSync(tmp)
  fs.mkdirSync(bin)
  fs.writeFileSync(path.join(bin, 'npm'), STUB_NPM, { mode: 0o755 })
  fs.writeFileSync(mountinfo, '')

  write('package.json', '{"name":"app"}\n')
  write('package-lock.json', LOCKFILE)
  // A stale install carried over in the node_modules volume.
  write('node_modules/next/package.json', '{"name":"next","version":"16.4.3"}')
  write('node_modules/next/dist/old-only.js', 'stale')
  write('node_modules/.lockfile-sha256', 'stale-hash\n')
})

afterEach(() => {
  fs.rmSync(root, { recursive: true, force: true })
})

describe('sync-dev-node-modules.sh', () => {
  it('leaves no staging directory behind when the install fails, across a restart loop', () => {
    // A container killed mid-install earlier left a partial staging tree.
    fs.mkdirSync(
      path.join(tmp, 'benger-node-modules-staging/node_modules/junk'),
      {
        recursive: true,
      },
    )

    for (let attempt = 0; attempt < 3; attempt++) {
      const result = run('fail')
      expect(result.status).not.toBe(0)
      expect(fs.readdirSync(tmp)).toEqual([])
    }

    expect(npmCalls()).toHaveLength(3)
    // The existing install is untouched, so the next start retries.
    expect(read('node_modules/next/package.json')).toContain('16.4.3')
    expect(read('node_modules/next/dist/old-only.js')).toBe('stale')
    expect(read('node_modules/.lockfile-sha256')).toBe('stale-hash\n')
  })

  it('replaces a stale install, keeps mounted packages and stamps the lockfile hash', () => {
    write('node_modules/@overlay/pkg/index.ts', 'overlay source')
    write('node_modules/@overlay/stale-sibling/index.js', 'stale')
    fs.writeFileSync(
      mountinfo,
      [
        `36 25 0:32 / ${app} rw,relatime - btrfs /dev/x rw`,
        `37 36 0:33 / ${app}/node_modules rw,relatime - btrfs /dev/y rw`,
        `38 36 0:32 /src ${app}/node_modules/@overlay/pkg ro,relatime - btrfs /dev/x ro`,
      ].join('\n') + '\n',
    )

    const result = run('succeed')

    expect(result.status).toBe(0)
    expect(npmCalls()).toEqual([
      `${path.join(tmp, 'benger-node-modules-staging')} ci --no-audit --no-fund`,
    ])
    expect(read('node_modules/next/package.json')).toContain('16.4.6')
    expect(read('node_modules/.bin/next')).toBe('fresh\n')
    expect(
      fs.existsSync(path.join(app, 'node_modules/next/dist/old-only.js')),
    ).toBe(false)
    expect(
      fs.existsSync(path.join(app, 'node_modules/@overlay/stale-sibling')),
    ).toBe(false)
    expect(read('node_modules/@overlay/pkg/index.ts')).toBe('overlay source')
    expect(read('node_modules/.lockfile-sha256').trim()).toBe(lockHash)
    expect(fs.readdirSync(tmp)).toEqual([])
  })

  it('does not reinstall when the stamp matches the lockfile', () => {
    write('node_modules/.lockfile-sha256', `${lockHash}\n`)

    const result = run('succeed')

    expect(result.status).toBe(0)
    expect(npmCalls()).toEqual([])
    expect(read('node_modules/next/package.json')).toContain('16.4.3')
  })
})
