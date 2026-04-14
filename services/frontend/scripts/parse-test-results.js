const fs = require('fs')

let raw = fs.readFileSync(process.argv[2] || 'test-output.json', 'utf8')
// Find the start of JSON (starts with '{')
const jsonStart = raw.indexOf('{')
if (jsonStart > 0) {
  raw = raw.substring(jsonStart)
}
const data = JSON.parse(raw)

const failedTests = []

function processSuite(suite, filePath = '') {
  const currentFile = suite.file || filePath

  if (suite.specs) {
    for (const spec of suite.specs) {
      for (const test of spec.tests || []) {
        if (
          test.status !== 'expected' &&
          test.status !== 'passed' &&
          test.status !== 'skipped'
        ) {
          failedTests.push({
            file: currentFile,
            title: spec.title,
            status: test.status,
            error:
              test.results?.[0]?.error?.message
                ?.split('\n')[0]
                ?.substring(0, 100) || 'Unknown',
          })
        }
      }
    }
  }

  if (suite.suites) {
    for (const s of suite.suites) {
      processSuite(s, currentFile)
    }
  }
}

for (const suite of data.suites || []) {
  processSuite(suite)
}

// Group by file
const byFile = {}
for (const t of failedTests) {
  if (!byFile[t.file]) byFile[t.file] = []
  byFile[t.file].push(t)
}

console.log('FAILED TESTS BY FILE:\n')
for (const [file, tests] of Object.entries(byFile)) {
  console.log('FILE: ' + file)
  console.log('  Failed: ' + tests.length)
  for (const t of tests.slice(0, 3)) {
    console.log('  - ' + t.title.substring(0, 60))
    console.log('    Error: ' + (t.error || 'Unknown'))
  }
  if (tests.length > 3) console.log('  ... and ' + (tests.length - 3) + ' more')
  console.log('')
}

console.log(
  '\nTOTAL: ' +
    failedTests.length +
    ' failures in ' +
    Object.keys(byFile).length +
    ' files'
)
