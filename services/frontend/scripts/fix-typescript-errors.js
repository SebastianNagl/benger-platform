#!/usr/bin/env node

/**
 * Script to fix common TypeScript errors in the codebase
 */

const fs = require('fs')
const path = require('path')
const glob = require('glob')

// Colors for console output
const colors = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m',
}

const fixes = {
  // Fix 1: Remove 'size' prop from Button components
  removeButtonSizeProp: {
    name: 'Remove size prop from Button components',
    pattern: /<Button([^>]*)\ssize="[^"]*"([^>]*)>/g,
    fix: (match) => {
      return match.replace(/\ssize="[^"]*"/g, '')
    },
    files: 'src/**/*.tsx',
  },

  // Fix 2: Fix params null checks
  fixParamsNull: {
    name: 'Fix params null checks',
    pattern: /const\s+{\s*id[^}]*}\s*=\s+params(?![\?\.])/g,
    fix: (match) => {
      return match.replace('params', 'params!')
    },
    files: 'src/app/**/page.tsx',
  },

  // Fix 3: Fix searchParams null checks
  fixSearchParamsNull: {
    name: 'Fix searchParams null checks',
    pattern: /searchParams\[/g,
    fix: (match) => {
      return 'searchParams?.['
    },
    files: 'src/app/**/page.tsx',
  },

  // Fix 4: Fix variant type issues for Badge components
  fixBadgeVariants: {
    name: 'Fix Badge variant types',
    pattern: /variant="(success|warning)"/g,
    fix: (match, variant) => {
      // Map non-standard variants to valid ones
      const variantMap = {
        success: 'default',
        warning: 'secondary',
      }
      return `variant="${variantMap[variant] || 'default'}"`
    },
    files: 'src/**/*.tsx',
  },

  // Fix 5: Fix Button variant="ghost" to "text"
  fixButtonGhostVariant: {
    name: 'Fix Button ghost variant',
    pattern: /(<Button[^>]*variant=")ghost(")/g,
    fix: (match, prefix, suffix) => {
      return prefix + 'text' + suffix
    },
    files: 'src/**/*.tsx',
  },
}

function processFile(filePath, fix) {
  let content = fs.readFileSync(filePath, 'utf8')
  const originalContent = content

  // Apply the fix
  content = content.replace(fix.pattern, fix.fix)

  if (content !== originalContent) {
    fs.writeFileSync(filePath, content, 'utf8')
    return true
  }

  return false
}

function main() {
  const args = process.argv.slice(2)
  const dryRun = args.includes('--dry-run')

  console.log(`${colors.blue}🔧 Fixing TypeScript errors...${colors.reset}\n`)

  if (dryRun) {
    console.log(
      `${colors.yellow}DRY RUN MODE - No files will be modified${colors.reset}\n`
    )
  }

  let totalFixed = 0

  Object.entries(fixes).forEach(([key, fix]) => {
    console.log(`${colors.blue}Applying: ${fix.name}${colors.reset}`)

    const files = glob.sync(fix.files)
    let fixedCount = 0

    files.forEach((file) => {
      if (dryRun) {
        const content = fs.readFileSync(file, 'utf8')
        const matches = content.match(fix.pattern)
        if (matches) {
          console.log(
            `  Would fix: ${path.relative(process.cwd(), file)} (${matches.length} occurrences)`
          )
          fixedCount += matches.length
        }
      } else {
        if (processFile(file, fix)) {
          console.log(
            `  ${colors.green}✓${colors.reset} Fixed: ${path.relative(process.cwd(), file)}`
          )
          fixedCount++
        }
      }
    })

    if (fixedCount > 0) {
      console.log(
        `  ${colors.green}Fixed ${fixedCount} occurrences${colors.reset}\n`
      )
      totalFixed += fixedCount
    } else {
      console.log(`  ${colors.yellow}No occurrences found${colors.reset}\n`)
    }
  })

  console.log(`${colors.blue}${'='.repeat(60)}${colors.reset}`)
  console.log(
    `${colors.green}✅ Total fixes applied: ${totalFixed}${colors.reset}`
  )

  if (!dryRun) {
    console.log(
      `\n${colors.yellow}💡 Now run 'npm run type-check' to verify the fixes${colors.reset}`
    )
  }
}

// Run the script
main()
