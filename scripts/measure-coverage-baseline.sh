#!/bin/bash

# Coverage Baseline Measurement Script
# Part of Issue #362: Set up Jest Coverage Infrastructure
#
# This script measures the current Jest coverage baseline for the frontend
# and tracks progression toward the 90%+ coverage goal.

set -e

echo "📊 Jest Coverage Baseline Measurement - BenGER Frontend"
echo "======================================================="
echo "Date: $(date)"
echo ""

# Navigate to frontend directory
cd "$(dirname "$0")/../services/frontend"

# Ensure dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm ci
fi

# Clean previous coverage data
echo "🧹 Cleaning previous coverage data..."
rm -rf coverage/ .jest-cache/

echo ""
echo "🧪 Running Jest tests with coverage collection..."
echo "💡 This may take a few moments to process all source files..."
echo ""

# Run tests with coverage
npm run test:ci > coverage-baseline.txt 2>&1 || {
    echo "⚠️  Some tests failed, but coverage data should still be collected"
    echo "📝 Check coverage-baseline.txt for detailed test results"
}

# Extract coverage data from the output
echo ""
echo "📊 Coverage Baseline Results:"
echo "=============================="

if [ -f "coverage-baseline.txt" ]; then
    # Extract the coverage table from the output
    echo "📈 Current Coverage Statistics:"
    echo ""
    
    # Look for coverage summary in the file
    if grep -A 20 "All files" coverage-baseline.txt > /dev/null 2>&1; then
        grep -A 20 "All files" coverage-baseline.txt | head -20
    else
        echo "⚠️  Coverage summary not found in test output"
        echo "📝 Full test output available in coverage-baseline.txt"
    fi
    
    echo ""
    echo "📁 Detailed coverage report available at:"
    echo "   - HTML Report: coverage/lcov-report/index.html"
    echo "   - LCOV File: coverage/lcov.info"
    echo "   - JSON Data: coverage/coverage-final.json"
    echo ""
    
    # Record baseline timestamp
    echo "Baseline coverage measured at $(date)" >> coverage-baseline.txt
    echo "Target progression toward 90%+ coverage (Phase 3 of Issue #294)" >> coverage-baseline.txt
    
    echo "✅ Coverage baseline measurement completed"
    echo "📄 Results saved to coverage-baseline.txt"
    
else
    echo "❌ Failed to generate coverage baseline file"
    exit 1
fi

echo ""
echo "🎯 Coverage Progression Plan:"
echo "=============================="
echo "📊 Current Status: Baseline measured (Issue #362 Phase 2)"
echo "🎯 Next Target: Achieve 40% statements coverage"
echo "🚀 Final Goal: 90%+ statements coverage (Issue #294 Phase 3)"
echo ""
echo "💡 To view coverage report:"
echo "   npm run coverage:open  # Opens HTML report in browser"
echo ""
echo "📝 Next steps:"
echo "1. Review coverage/lcov-report/index.html for detailed gaps"
echo "2. Prioritize uncovered critical paths and utilities"
echo "3. Add tests incrementally while maintaining quality"
echo "4. Monitor progress with this script"