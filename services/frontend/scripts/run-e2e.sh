#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"

cd "$FRONTEND_DIR"

echo "🚀 BenGER E2E Test Runner"
echo "=========================="

show_usage() {
    echo "Usage: $0 [OPTIONS] [TEST_SUITE]"
    echo ""
    echo "TEST_SUITES:"
    echo "  all           Run all E2E tests (default)"
    echo "  user-journeys Run user journey tests (registration, project lifecycle)"
    echo "  multi-org     Run multi-organization collaboration tests"
    echo "  error-recovery Run error recovery and resilience tests"
    echo "  mobile        Run mobile and responsive tests"
    echo "  cross-browser Run cross-browser compatibility tests"
    echo "  visual        Run visual regression tests"
    echo ""
    echo "OPTIONS:"
    echo "  -h, --help    Show this help message"
    echo "  --debug       Run with debug output"
    echo "  --headed      Run in headed mode (show browser)"
    echo "  --workers N   Set number of parallel workers"
    echo "  --timeout N   Set timeout in seconds"
    echo "  --update-snapshots  Update visual regression snapshots"
    echo "  --report      Show HTML report after tests"
}

DEBUG=""
HEADED=""
WORKERS=""
TIMEOUT=""
UPDATE_SNAPSHOTS=""
SHOW_REPORT=""
TEST_SUITE="all"

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        --debug)
            DEBUG="--debug"
            shift
            ;;
        --headed)
            HEADED="--headed"
            shift
            ;;
        --workers)
            WORKERS="--workers=$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="--timeout=$((${2} * 1000))"
            shift 2
            ;;
        --update-snapshots)
            UPDATE_SNAPSHOTS="--update-snapshots"
            shift
            ;;
        --report)
            SHOW_REPORT="--reporter=html"
            shift
            ;;
        all|user-journeys|multi-org|error-recovery|mobile|cross-browser|visual)
            TEST_SUITE="$1"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

check_dependencies() {
    echo "🔍 Checking dependencies..."
    
    if ! command -v npm &> /dev/null; then
        echo "❌ npm is not installed"
        exit 1
    fi
    
    if ! npm list @playwright/test &> /dev/null; then
        echo "❌ Playwright is not installed. Run: npm install"
        exit 1
    fi
    
    echo "✅ Dependencies check passed"
}

install_browsers() {
    echo "🌐 Installing browser dependencies..."
    npx playwright install
    echo "✅ Browsers installed"
}

start_dev_server() {
    echo "🏗️ Starting development server..."
    
    if lsof -Pi :3000 -sTCP:LISTEN -t >/dev/null; then
        echo "✅ Development server already running on port 3000"
        return
    fi
    
    npm run dev &
    DEV_SERVER_PID=$!
    
    echo "⏳ Waiting for development server to start..."
    for i in {1..30}; do
        if curl -s http://localhost:3000 >/dev/null 2>&1; then
            echo "✅ Development server is ready"
            return
        fi
        sleep 2
    done
    
    echo "❌ Development server failed to start"
    kill $DEV_SERVER_PID 2>/dev/null || true
    exit 1
}

cleanup() {
    echo "🧹 Cleaning up..."
    if [[ -n $DEV_SERVER_PID ]]; then
        kill $DEV_SERVER_PID 2>/dev/null || true
    fi
}

trap cleanup EXIT

run_tests() {
    local suite=$1
    echo "🧪 Running $suite tests..."
    
    local cmd="npx playwright test"
    
    if [[ -n $DEBUG ]]; then
        cmd="$cmd $DEBUG"
    fi
    
    if [[ -n $HEADED ]]; then
        cmd="$cmd $HEADED"
    fi
    
    if [[ -n $WORKERS ]]; then
        cmd="$cmd $WORKERS"
    fi
    
    if [[ -n $TIMEOUT ]]; then
        cmd="$cmd $TIMEOUT"
    fi
    
    if [[ -n $UPDATE_SNAPSHOTS ]]; then
        cmd="$cmd $UPDATE_SNAPSHOTS"
    fi
    
    if [[ -n $SHOW_REPORT ]]; then
        cmd="$cmd $SHOW_REPORT"
    fi
    
    case $suite in
        all)
            cmd="$cmd e2e/"
            ;;
        user-journeys)
            cmd="$cmd e2e/user-journeys/"
            ;;
        multi-org)
            cmd="$cmd e2e/multi-org/"
            ;;
        error-recovery)
            cmd="$cmd e2e/error-recovery/"
            ;;
        mobile)
            cmd="$cmd e2e/cross-platform/mobile.spec.ts --project=mobile-chrome --project=mobile-safari --project=tablet"
            ;;
        cross-browser)
            cmd="$cmd e2e/cross-platform/mobile.spec.ts --project=chromium --project=firefox --project=webkit"
            ;;
        visual)
            cmd="$cmd e2e/visual/ --project=visual-regression"
            ;;
        *)
            echo "❌ Unknown test suite: $suite"
            exit 1
            ;;
    esac
    
    echo "🏃 Running: $cmd"
    $cmd
}

generate_report() {
    echo "📊 Generating test report..."
    
    if [[ -f "playwright-report/index.html" ]]; then
        echo "✅ Test report available at: playwright-report/index.html"
        
        if command -v open &> /dev/null; then
            read -p "Open report in browser? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                open playwright-report/index.html
            fi
        fi
    fi
}

main() {
    echo "🎯 Test Suite: $TEST_SUITE"
    echo "⚙️  Options: $DEBUG $HEADED $WORKERS $TIMEOUT $UPDATE_SNAPSHOTS $SHOW_REPORT"
    echo ""
    
    check_dependencies
    install_browsers
    start_dev_server
    
    echo ""
    run_tests "$TEST_SUITE"
    
    echo ""
    echo "🎉 Test execution completed!"
    
    if [[ -n $SHOW_REPORT ]] || [[ $TEST_SUITE == "visual" ]]; then
        generate_report
    fi
}

main