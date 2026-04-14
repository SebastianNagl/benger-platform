#!/bin/bash
# Context-safe E2E test runner
# Runs all E2E tests and outputs only a concise summary to avoid context overflow

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_FILE="$FRONTEND_DIR/test-output.json"
SUMMARY_FILE="$FRONTEND_DIR/test-summary.txt"

cd "$FRONTEND_DIR"

echo "Running E2E tests (output to $OUTPUT_FILE)..."

# Run tests with JSON reporter, capture exit code
E2E_ISOLATED=true \
E2E_CLEANUP=false \
PLAYWRIGHT_BASE_URL=http://benger-test.localhost:8090 \
npx playwright test \
  --project=role-scenarios \
  --project=chromium \
  --project=enhanced-workflows \
  --project=user-workflows \
  --project=feature-tests \
  --project=admin \
  --retries=0 \
  --timeout=30000 \
  --reporter=json \
  > "$OUTPUT_FILE" 2>&1

TEST_EXIT_CODE=$?

# Parse JSON and create summary
node -e "
const fs = require('fs');

try {
  const raw = fs.readFileSync('$OUTPUT_FILE', 'utf8');
  const data = JSON.parse(raw);

  let passed = 0;
  let failed = 0;
  let skipped = 0;
  const failedTests = [];

  // Walk through suites recursively
  function processSuite(suite, filePath = '') {
    const currentFile = suite.file || filePath;

    // Process specs in this suite
    if (suite.specs) {
      for (const spec of suite.specs) {
        for (const test of spec.tests || []) {
          const status = test.status;
          if (status === 'expected' || status === 'passed') {
            passed++;
          } else if (status === 'skipped') {
            skipped++;
          } else {
            failed++;
            failedTests.push({
              file: currentFile,
              title: spec.title,
              error: test.results?.[0]?.error?.message?.split('\\n')[0] || 'Unknown error'
            });
          }
        }
      }
    }

    // Process nested suites
    if (suite.suites) {
      for (const nestedSuite of suite.suites) {
        processSuite(nestedSuite, currentFile);
      }
    }
  }

  // Process all top-level suites
  for (const suite of data.suites || []) {
    processSuite(suite);
  }

  // Generate summary
  let summary = '=== E2E TEST SUMMARY ===\\n';
  summary += 'Passed: ' + passed + '\\n';
  summary += 'Failed: ' + failed + '\\n';
  summary += 'Skipped: ' + skipped + '\\n';
  summary += 'Total: ' + (passed + failed + skipped) + '\\n';

  if (failedTests.length > 0) {
    summary += '\\n=== FAILED TESTS ===\\n';
    for (const t of failedTests) {
      summary += '\\n- ' + t.file + '\\n';
      summary += '  Test: ' + t.title + '\\n';
      summary += '  Error: ' + t.error.substring(0, 200) + '\\n';
    }
  }

  if (failed === 0) {
    summary += '\\nAll tests passed!\\n';
  }

  console.log(summary);
  fs.writeFileSync('$SUMMARY_FILE', summary);

} catch (e) {
  // JSON parsing failed - likely non-JSON output (errors)
  console.log('=== E2E TEST SUMMARY ===');
  console.log('Error: Could not parse test results');
  console.log('Check $OUTPUT_FILE for details');
  console.log('');
  // Show last 30 lines of output for debugging
  const raw = fs.readFileSync('$OUTPUT_FILE', 'utf8');
  const lines = raw.split('\\n');
  console.log('Last 30 lines of output:');
  console.log(lines.slice(-30).join('\\n'));
}
"

echo ""
echo "Summary saved to: $SUMMARY_FILE"
echo "Full output saved to: $OUTPUT_FILE"

exit $TEST_EXIT_CODE
