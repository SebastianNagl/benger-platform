#!/usr/bin/env node
/**
 * Mutation-score gate — the co-gate for the frontend coverage ratchet.
 *
 * Parses a Stryker JSON report (the mutation-testing-report-schema "mutation
 * test result" format), computes the mutation score per mutated file, and
 * enforces each file's floor from mutation-floors.json. Always prints a table
 * (score, floor, delta, suggested bump) so a passing run still shows headroom;
 * exits non-zero only on a real regression below floor.
 *
 * This mirrors services/workers/scripts/mutation_gate.py in spirit. We gate
 * here rather than via Stryker's own `thresholds.break` so a single-mutant
 * flake can't red-light the nightly job — the floor is the contract.
 *
 * Mutation score = killed / (killed + survived). Excluded from the denominator:
 * Timeout, NoCoverage, RuntimeError, CompileError, Ignored, Pending (Stryker
 * convention — only Killed and Survived are "covered & decided").
 *
 * Usage:
 *   node scripts/mutation-gate.js
 *   node scripts/mutation-gate.js --report reports/mutation/mutation.json \
 *       --floors mutation-floors.json
 */
'use strict'

const fs = require('fs')
const path = require('path')

function parseArgs(argv) {
  const args = {
    report: 'reports/mutation/mutation.json',
    floors: 'mutation-floors.json',
  }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--report') args.report = argv[++i]
    else if (a === '--floors') args.floors = argv[++i]
    else if (a === '--help' || a === '-h') {
      console.log(
        'Usage: node scripts/mutation-gate.js [--report <json>] [--floors <json>]',
      )
      process.exit(0)
    }
  }
  return args
}

// Statuses that count as "decided & covered" — only these form the denominator.
const KILLED = new Set(['Killed'])
const SURVIVED = new Set(['Survived'])

/**
 * Reduce a Stryker JSON report to per-file { killed, survived, excluded }.
 * The schema nests mutants under report.files[<path>].mutants[].status.
 */
function tallyByFile(report) {
  const files = report && report.files
  if (!files || typeof files !== 'object') {
    throw new Error(
      'report has no "files" map — is this a Stryker mutation JSON report?',
    )
  }
  const tally = {}
  for (const [filePath, entry] of Object.entries(files)) {
    const mutants = (entry && entry.mutants) || []
    let killed = 0
    let survived = 0
    let excluded = 0
    for (const m of mutants) {
      if (KILLED.has(m.status)) killed++
      else if (SURVIVED.has(m.status)) survived++
      else excluded++ // Timeout / NoCoverage / RuntimeError / CompileError / ...
    }
    tally[filePath] = { killed, survived, excluded }
  }
  return tally
}

function loadFloors(floorsPath) {
  const raw = JSON.parse(fs.readFileSync(floorsPath, 'utf8'))
  const floors = {}
  for (const [k, v] of Object.entries(raw)) {
    if (k.startsWith('_')) continue // skip _comment et al.
    if (typeof v === 'number') floors[k] = v
  }
  return floors
}

function main() {
  const args = parseArgs(process.argv)
  const reportPath = path.resolve(args.report)
  const floorsPath = path.resolve(args.floors)

  if (!fs.existsSync(reportPath)) {
    console.error(
      `::error::mutation report not found at ${reportPath} — run ` +
        `\`npm run test:mutation\` first (it writes ${args.report}).`,
    )
    process.exit(2)
  }

  const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'))
  const tally = tallyByFile(report)
  const floors = loadFloors(floorsPath)

  // Gate every file that has a floor. (A file in the report but absent from
  // floors is informational; a floored file absent from the report is a hard
  // error — its tests stopped running.)
  const flooredPaths = Object.keys(floors)
  const rows = []
  let failed = false

  // Build the union so we still surface report-only files in the table.
  const allPaths = new Set([...flooredPaths, ...Object.keys(tally)])

  for (const filePath of [...allPaths].sort()) {
    const t = tally[filePath]
    const hasFloor = Object.prototype.hasOwnProperty.call(floors, filePath)
    const floor = hasFloor ? floors[filePath] : null

    if (!t) {
      // Floored file missing from report → tests vanished. Hard fail.
      rows.push({
        filePath,
        score: null,
        floor,
        killed: 0,
        survived: 0,
        excluded: 0,
        ok: false,
        missing: true,
      })
      failed = true
      continue
    }

    const denom = t.killed + t.survived
    const score = denom === 0 ? 100 : (t.killed / denom) * 100
    const ok = !hasFloor || score + 1e-9 >= floor
    if (hasFloor && !ok) failed = true
    rows.push({
      filePath,
      score,
      floor,
      killed: t.killed,
      survived: t.survived,
      excluded: t.excluded,
      ok,
      missing: false,
    })
  }

  // --- Print table -------------------------------------------------------
  const bar = '─'.repeat(96)
  console.log(bar)
  console.log(`Mutation gate [${failed ? 'FAIL' : 'PASS'}]`)
  console.log(bar)
  const header =
    'file'.padEnd(44) +
    'score'.padStart(8) +
    'floor'.padStart(7) +
    'delta'.padStart(8) +
    'bump'.padStart(6) +
    '  k/s/x'
  console.log(header)
  console.log('-'.repeat(96))
  for (const r of rows) {
    if (r.missing) {
      console.log(
        r.filePath.padEnd(44) +
          'MISSING'.padStart(8) +
          String(r.floor).padStart(7) +
          '—'.padStart(8) +
          '—'.padStart(6) +
          '  (not in report — tests stopped running)',
      )
      continue
    }
    const scoreStr = r.score.toFixed(2)
    const floorStr = r.floor === null ? '—' : String(r.floor)
    const deltaStr =
      r.floor === null ? '—' : (r.score - r.floor >= 0 ? '+' : '') + (r.score - r.floor).toFixed(2)
    const bump = String(Math.floor(r.score)) // suggested ratchet target
    const mark = r.floor !== null && !r.ok ? ' ✗' : ''
    console.log(
      r.filePath.padEnd(44) +
        scoreStr.padStart(8) +
        floorStr.padStart(7) +
        deltaStr.padStart(8) +
        bump.padStart(6) +
        `  ${r.killed}/${r.survived}/${r.excluded}${mark}`,
    )
  }
  console.log(bar)
  console.log('k=killed  s=survived  x=excluded (timeout/no-coverage/error)')
  console.log(
    'ratchet: when a score rises, bump its floor in mutation-floors.json to the "bump" value.',
  )
  console.log(bar)

  if (failed) {
    for (const r of rows) {
      if (r.missing) {
        console.error(
          `::error::${r.filePath} has floor ${r.floor} but no mutants in the ` +
            `report — its tests stopped running (or it left the mutate scope).`,
        )
      } else if (r.floor !== null && !r.ok) {
        console.error(
          `::error::mutation score ${r.score.toFixed(2)}% for ${r.filePath} is ` +
            `below floor ${r.floor}% — a test was weakened or new code lacks a ` +
            `killing assertion. Strengthen the tests (don't lower the floor).`,
        )
      }
    }
    process.exit(1)
  }
}

main()
