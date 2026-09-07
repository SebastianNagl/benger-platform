#!/usr/bin/env node
/**
 * Merge Jest coverage from sharded runs and enforce jest.config.js's
 * coverageThreshold on the MERGED map.
 *
 * `jest --shard=N/M` evaluates thresholds per shard, so a global floor (or a
 * per-directory floor whose files land in another shard) fails spuriously.
 * CI therefore runs each shard with `--coverageThreshold='{}'` and
 * `--coverageReporters=json`, uploads coverage/coverage-final.json, and this
 * script applies the real floors once, mirroring Jest's semantics:
 *   - a non-"global" key is a path or glob; the files it matches form ONE
 *     group with its own floor and are excluded from the global floor
 *   - positive numbers are minimum percentages (the only form used here)
 *
 * Usage: node scripts/coverage-gate.mjs <coverage-final.json ...>
 */
import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const {
  createCoverageMap,
  createCoverageSummary,
} = require('istanbul-lib-coverage')
const micromatch = require('micromatch')

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const thresholds = require(path.join(root, 'jest.config.js')).coverageThreshold
const inputs = process.argv.slice(2)
if (inputs.length === 0) {
  console.error('usage: coverage-gate.mjs <coverage-final.json ...>')
  process.exit(2)
}

const map = createCoverageMap({})
for (const file of inputs) map.merge(JSON.parse(fs.readFileSync(file, 'utf8')))
const allFiles = map.files()
console.log(
  `merged ${inputs.length} coverage file(s), ${allFiles.length} source files`,
)

const KEYS = ['statements', 'branches', 'functions', 'lines']
let failed = false

function summarize(files) {
  const summary = createCoverageSummary()
  for (const f of files) summary.merge(map.fileCoverageFor(f).toSummary())
  return summary
}

function check(label, summary, spec) {
  for (const key of KEYS) {
    const floor = spec[key]
    if (floor == null) continue
    if (floor < 0) {
      console.warn(
        `${label}: negative (max-uncovered) thresholds are not supported here; skipping ${key}`,
      )
      continue
    }
    const pct = summary[key].pct
    const ok = pct >= floor
    if (!ok) failed = true
    console.log(
      `${ok ? 'ok  ' : 'FAIL'} ${label} ${key}: ${pct.toFixed(2)}% (floor ${floor}%)`,
    )
  }
}

const grouped = new Set()
for (const [key, spec] of Object.entries(thresholds)) {
  if (key === 'global') continue
  const abs = path.resolve(root, key)
  const matched = allFiles.filter(
    (f) =>
      f.startsWith(abs) ||
      micromatch.isMatch(f, abs) ||
      micromatch.isMatch(path.relative(root, f), key),
  )
  if (matched.length === 0) {
    console.warn(`no files matched threshold key "${key}"`)
    continue
  }
  matched.forEach((f) => grouped.add(f))
  check(`"${key}" (${matched.length} files)`, summarize(matched), spec)
}
if (thresholds.global) {
  const rest = allFiles.filter((f) => !grouped.has(f))
  check(`"global" (${rest.length} files)`, summarize(rest), thresholds.global)
}

if (failed) {
  console.error('coverage thresholds not met')
  process.exit(1)
}
console.log('coverage thresholds met')
