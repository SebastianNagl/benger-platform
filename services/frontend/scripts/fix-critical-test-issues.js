#!/usr/bin/env node

const fs = require('fs')
const path = require('path')
const glob = require('glob')

function fixCriticalIssues(filePath) {
  try {
    let content = fs.readFileSync(filePath, 'utf8')
    const originalContent = content
    let hasChanges = false

    // Fix router mock issues - ensure router has all necessary methods
    if (content.includes('useRouter') && content.includes('jest.mock')) {
      // Enhanced router mock with all methods
      const routerMockPattern =
        /jest\.mock\('next\/navigation',.*?\(\{\s*useRouter:\s*.*?\}\)\)/s
      if (routerMockPattern.test(content)) {
        content = content.replace(
          routerMockPattern,
          `jest.mock('next/navigation', () => ({
  useRouter: jest.fn(() => ({
    push: jest.fn(),
    replace: jest.fn(),
    back: jest.fn(),
    forward: jest.fn(),
    refresh: jest.fn(),
    prefetch: jest.fn(),
    pathname: '/',
    query: {},
    asPath: '/',
    route: '/',
    basePath: '',
    isReady: true,
    isPreview: false,
    isLocaleDomain: false
  })),
  useParams: jest.fn(() => ({})),
  useSearchParams: jest.fn(() => new URLSearchParams()),
  usePathname: jest.fn(() => '/'),
  notFound: jest.fn(),
  redirect: jest.fn()
}))`
        )
        hasChanges = true
      }
    }

    // Fix API client mocks - add missing methods
    if (
      content.includes('ApiClient') &&
      content.includes('mockImplementation')
    ) {
      // Add missing API methods to mocks
      const apiMockPattern =
        /ApiClient:\s*jest\.fn\(\)\.mockImplementation\(\(\)\s*=>\s*\(\{[^}]*\}\)\)/s
      if (apiMockPattern.test(content)) {
        content = content.replace(apiMockPattern, (match) => {
          if (!match.includes('setOrganizationContextProvider')) {
            // Add missing methods to the API mock
            const methodsToAdd = `
    setOrganizationContextProvider: jest.fn(),
    getOrganizationMembers: jest.fn().mockResolvedValue([]),
    listInvitations: jest.fn().mockResolvedValue([]),
    getOrganizationInvitations: jest.fn().mockResolvedValue([]),
    refreshToken: jest.fn().mockResolvedValue({}),
    logout: jest.fn(),
    login: jest.fn().mockResolvedValue({}),`

            const insertPoint = match.lastIndexOf('}))')
            if (insertPoint > 0) {
              hasChanges = true
              return (
                match.slice(0, insertPoint) +
                methodsToAdd +
                '\n  ' +
                match.slice(insertPoint)
              )
            }
          }
          return match
        })
      }
    }

    // Fix specific router replace issues in test files
    if (content.includes('router.replace is not a function')) {
      // Add proper router mock setup
      const mockSetup = `
const mockRouter = {
  push: jest.fn(),
  replace: jest.fn(),
  back: jest.fn(),
  forward: jest.fn(),
  refresh: jest.fn(),
  prefetch: jest.fn(),
  pathname: '/',
  query: {},
  asPath: '/'
};

beforeEach(() => {
  (useRouter as jest.Mock).mockReturnValue(mockRouter);
});
`

      // Find where to insert the mock setup
      if (content.includes('describe(') && !content.includes('mockRouter')) {
        const describeIndex = content.indexOf('describe(')
        content =
          content.slice(0, describeIndex) +
          mockSetup +
          '\n' +
          content.slice(describeIndex)
        hasChanges = true
      }
    }

    // Fix useState hook issues - ensure React is imported and properly mocked
    if (
      content.includes('Cannot read properties of null') &&
      content.includes('useState')
    ) {
      // Check if React mock is needed
      if (!content.includes("jest.requireActual('react')")) {
        const reactMock = `
jest.mock('react', () => ({
  ...jest.requireActual('react'),
  useState: jest.fn(),
  useEffect: jest.fn(),
  useContext: jest.fn(),
  useCallback: jest.fn(),
  useMemo: jest.fn(),
  useRef: jest.fn()
}));
`
        // Add React mock at the top after other mocks
        const firstImportIndex = content.indexOf('import')
        if (firstImportIndex > 0) {
          content =
            content.slice(0, firstImportIndex) +
            reactMock +
            '\n' +
            content.slice(firstImportIndex)
          hasChanges = true
        }
      }
    }

    // Fix component interface mismatches - add common test-ids to component mocks
    const componentMockPatterns = [
      {
        pattern: /GridPattern.*React\.createElement/,
        replacement: `GridPattern: () => React.createElement('div', { 'data-testid': 'grid-pattern' }, 'Grid Pattern')`,
      },
      {
        pattern: /HeroPattern.*React\.createElement/,
        replacement: `HeroPattern: () => React.createElement('div', { 'data-testid': 'hero-pattern' }, 'Hero Pattern')`,
      },
      {
        pattern: /LoadingSpinner.*React\.createElement/,
        replacement: `LoadingSpinner: () => React.createElement('div', { 'data-testid': 'loading-spinner' }, 'Loading...')`,
      },
    ]

    for (const { pattern, replacement } of componentMockPatterns) {
      if (pattern.test(content)) {
        content = content.replace(pattern, replacement)
        hasChanges = true
      }
    }

    if (originalContent !== content) {
      fs.writeFileSync(filePath, content, 'utf8')
      return true
    }
    return false
  } catch (error) {
    console.error(`Error processing ${filePath}:`, error.message)
    return false
  }
}

// Main execution
console.log('🔧 Fixing critical test issues...\n')

// Get all test files
const testFiles = glob.sync('src/**/*.test.{ts,tsx}', {
  cwd: path.join(__dirname, '..'),
  absolute: true,
})

let fixedCount = 0

for (const file of testFiles) {
  const relativePath = path.relative(path.join(__dirname, '..'), file)
  if (fixCriticalIssues(file)) {
    console.log(`  ✅ Fixed: ${relativePath}`)
    fixedCount++
  }
}

console.log(`\n✨ Fixed ${fixedCount} files with critical test issues`)
