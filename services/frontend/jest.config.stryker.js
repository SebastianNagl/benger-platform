/**
 * Jest config used ONLY by Stryker's jest-runner (see stryker.conf.json).
 *
 * Why this exists instead of reusing jest.config.js directly:
 *
 * 1. FLAT, not dual-`projects`. The platform jest.config.js uses a two-entry
 *    `projects` array (client + api-routes). Stryker's jest-runner needs a
 *    single flat project, so we hoist the `client` project's settings to the
 *    top level here. (Equivalent to the `config: { projects: null }` override,
 *    but flattening here lets us also carry the client project's transform /
 *    moduleNameMapper, which a bare `projects: null` would drop.)
 *
 * 2. ABSOLUTE babel preset path. Stryker runs jest with cwd set to its sandbox
 *    (.stryker-tmp/sandbox-XXXX), which has no real node_modules of its own
 *    (just a symlink). Babel resolves a *bare* preset string like 'next/babel'
 *    relative to cwd, so from the sandbox cwd it fails with
 *    "Cannot find module 'next/babel'" — and silently falls back to parsing the
 *    file as plain JS, which then chokes on TypeScript type annotations
 *    ("Missing initializer in const declaration"). Resolving the preset to an
 *    absolute path here makes it cwd-independent and the TS files transform
 *    correctly inside the sandbox.
 *
 * This file changes nothing for the normal `jest` runs — those still use
 * jest.config.js.
 */
const path = require('path')
const baseConfig = require('./jest.config.js')

// The client (jsdom) project is the one that compiles src/lib/utils/*.
const clientProject = baseConfig.projects.find(
  (p) => p.displayName === 'client',
)

// Resolve the babel preset to an absolute path so it survives Stryker's
// sandbox cwd (see header note #2).
const nextBabel = require.resolve('next/babel')

/** @type {import('jest').Config} */
module.exports = {
  rootDir: __dirname,
  // Stryker's jest-runner needs its own environment to report per-test coverage
  // back to Stryker (coverageAnalysis: "perTest"). The base client project uses
  // plain 'jsdom'; swap in Stryker's jsdom mixin. See:
  // https://stryker-mutator.io/docs/stryker-js/jest-runner#coverage-analysis
  testEnvironment: '@stryker-mutator/jest-runner/jest-env/jsdom',
  setupFilesAfterEnv: clientProject.setupFilesAfterEnv,
  // SCOPE the initial test run to ONLY the dedicated tests of the mutated
  // crown jewels (stryker.conf.json `mutate`). The base clientProject.testMatch
  // globs ALL ~12.9k client tests, dozens of which carry a per-file
  // `@jest-environment <custom>` docblock that bypasses this config's env and
  // so does NOT report per-test coverage to Stryker — the initial "perTest" dry
  // run then aborts with "Missing coverage results for ...". Stryker only needs
  // the tests that exercise the mutated files; measuring the DEDICATED unit +
  // property + branch suites is also the honest signal (are our intentional
  // tests strong, not whether some incidental component test happens to cover a
  // mutant). Keep this list in sync with stryker.conf.json `mutate`.
  testMatch: [
    '<rootDir>/src/lib/utils/__tests__/annotationDiff*.test.{ts,tsx}',
    '<rootDir>/src/lib/utils/__tests__/fieldPath*.test.{ts,tsx}',
    '<rootDir>/src/lib/utils/__tests__/fieldMapping*.test.{ts,tsx}',
    '<rootDir>/src/lib/api/__tests__/evaluation-types*.test.{ts,tsx}',
  ],
  moduleNameMapper: {
    // Some test files carry a per-file `@jest-environment jsdom` docblock
    // (e.g. annotationDiff.br4.test.ts). That pragma resolves to the plain
    // 'jest-environment-jsdom' package, which does NOT report per-test
    // coverage to Stryker ("Missing coverage results for ..."). Redirect that
    // env to Stryker's jsdom mixin so docblock-pinned files still report.
    '^jest-environment-jsdom$':
      '@stryker-mutator/jest-runner/jest-env/jsdom',
    ...clientProject.moduleNameMapper,
  },
  moduleFileExtensions: clientProject.moduleFileExtensions,
  transform: {
    '^.+\\.(js|jsx|ts|tsx)$': [
      'babel-jest',
      {
        presets: [nextBabel],
        babelrc: false,
        configFile: false,
        compact: false,
      },
    ],
  },
  transformIgnorePatterns: baseConfig.transformIgnorePatterns,
  testPathIgnorePatterns: [
    ...baseConfig.testPathIgnorePatterns,
    // annotationDiff.br4.test.ts carries a per-file `@jest-environment jsdom`
    // docblock. jest resolves that pragma through its OWN env resolver (not
    // moduleNameMapper), pinning the plain jsdom env that doesn't report
    // per-test coverage to Stryker ("Missing coverage results for ..."). Its
    // coverage of annotationDiff.ts is fully redundant with
    // annotationDiff-branches.test.ts + annotationDiff.property.test.ts, so we
    // drop it from the Stryker run only (the normal `jest` run still includes
    // it). Mutant-killing power is unaffected — the same branches are covered.
    'annotationDiff\\.br4\\.test\\.ts$',
    // fieldPath.br7.test.ts carries the same `@jest-environment jsdom` docblock
    // and the same coverage-reporting problem; its fieldPath.ts branch coverage
    // is redundant with fieldPath.test.ts + fieldPath.property.test.ts.
    'fieldPath\\.br7\\.test\\.ts$',
  ],
  // Stryker measures mutation coverage itself; jest coverage just slows the run.
  collectCoverage: false,
  // Caching across mutant runs is unsafe — Stryker rewrites source per mutant.
  cache: false,
  // Quieter, and don't bail (Stryker needs the full per-test result set).
  bail: 0,
  verbose: false,
}
