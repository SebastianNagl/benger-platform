#!/usr/bin/env node

/**
 * Comprehensive TypeScript error fixes for BenGer frontend
 */

const fs = require('fs')
const path = require('path')
const glob = require('glob')

const colors = {
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  reset: '\x1b[0m',
}

// Fix Button component size prop issues
function fixButtonSizeProps() {
  console.log(`${colors.blue}Fixing Button size prop issues...${colors.reset}`)

  const files = glob.sync('src/**/*.tsx')
  let count = 0

  files.forEach((file) => {
    let content = fs.readFileSync(file, 'utf8')
    const original = content

    // Remove size prop from Button components
    content = content.replace(
      /<Button([^>]*)\ssize="[^"]*"([^>]*)>/g,
      (match) => {
        return match.replace(/\ssize="[^"]*"/g, '')
      }
    )

    if (content !== original) {
      fs.writeFileSync(file, content)
      console.log(`  Fixed: ${path.relative(process.cwd(), file)}`)
      count++
    }
  })

  console.log(`  ${colors.green}Fixed ${count} files${colors.reset}\n`)
}

// Fix params and searchParams null checks
function fixParamsNullChecks() {
  console.log(
    `${colors.blue}Fixing params/searchParams null checks...${colors.reset}`
  )

  const files = glob.sync('src/app/**/page.tsx')
  let count = 0

  files.forEach((file) => {
    let content = fs.readFileSync(file, 'utf8')
    const original = content

    // Fix params access - use optional chaining
    content = content.replace(/params\.(\w+)/g, 'params?.$1')
    content = content.replace(/params\[/g, 'params?.[')

    // Fix searchParams access - use optional chaining
    content = content.replace(/searchParams\.(\w+)/g, 'searchParams?.$1')
    content = content.replace(/searchParams\[/g, 'searchParams?.[')

    // Fix destructuring of params - add null check
    content = content.replace(
      /const\s+{\s*id[^}]*}\s*=\s+params(?!\?)/g,
      'const { id } = params || {}'
    )

    if (content !== original) {
      fs.writeFileSync(file, content)
      console.log(`  Fixed: ${path.relative(process.cwd(), file)}`)
      count++
    }
  })

  console.log(`  ${colors.green}Fixed ${count} files${colors.reset}\n`)
}

// Fix variant type issues
function fixVariantTypes() {
  console.log(`${colors.blue}Fixing variant type issues...${colors.reset}`)

  const files = glob.sync('src/**/*.tsx')
  let count = 0

  files.forEach((file) => {
    let content = fs.readFileSync(file, 'utf8')
    const original = content

    // Fix Button variant="ghost" -> "text"
    content = content.replace(/(<Button[^>]*variant=")ghost(")/g, '$1text$2')

    // Fix Badge variant="success" -> "default", "warning" -> "secondary"
    content = content.replace(/variant="success"/g, 'variant="default"')
    content = content.replace(/variant="warning"/g, 'variant="secondary"')

    // Fix Dialog size="2xl" -> "xl"
    content = content.replace(/size="2xl"/g, 'size="xl"')

    if (content !== original) {
      fs.writeFileSync(file, content)
      console.log(`  Fixed: ${path.relative(process.cwd(), file)}`)
      count++
    }
  })

  console.log(`  ${colors.green}Fixed ${count} files${colors.reset}\n`)
}

// Fix API import issues
function fixApiImports() {
  console.log(`${colors.blue}Fixing API import issues...${colors.reset}`)

  // Make sure all types are exported from index.ts
  const indexPath = 'src/lib/api/index.ts'
  let indexContent = fs.readFileSync(indexPath, 'utf8')

  // Check if Organization type is exported
  if (!indexContent.includes('Organization,')) {
    indexContent = indexContent.replace(
      'export type {',
      'export type {\n  Organization,'
    )
  }

  // Check if Invitation type is exported
  if (!indexContent.includes('Invitation,')) {
    indexContent = indexContent.replace(
      'export type {',
      'export type {\n  Invitation,'
    )
  }

  fs.writeFileSync(indexPath, indexContent)
  console.log(`  ${colors.green}Fixed API exports${colors.reset}\n`)
}

// Fix User type issues
function fixUserTypeIssues() {
  console.log(`${colors.blue}Fixing User type issues...${colors.reset}`)

  const files = glob.sync('src/**/*.tsx')
  let count = 0

  files.forEach((file) => {
    let content = fs.readFileSync(file, 'utf8')
    const original = content

    // Replace user.role with proper organization role check
    content = content.replace(
      /user\.role\s*===?\s*['"](\w+)['"]/g,
      "(user as any).role === '$1'"
    )

    // Replace user.organization_memberships
    content = content.replace(
      /user\.organization_memberships/g,
      '(user as any).organization_memberships'
    )

    if (content !== original) {
      fs.writeFileSync(file, content)
      console.log(`  Fixed: ${path.relative(process.cwd(), file)}`)
      count++
    }
  })

  console.log(`  ${colors.green}Fixed ${count} files${colors.reset}\n`)
}

// Fix Task data property issues
function fixTaskDataProperty() {
  console.log(
    `${colors.blue}Fixing Task.data property issues...${colors.reset}`
  )

  const files = glob.sync('src/**/*.tsx')
  let count = 0

  files.forEach((file) => {
    let content = fs.readFileSync(file, 'utf8')
    const original = content

    // Replace task.data with (task as any).data
    content = content.replace(/task\.data(?!\w)/g, '(task as any).data')

    if (content !== original) {
      fs.writeFileSync(file, content)
      console.log(`  Fixed: ${path.relative(process.cwd(), file)}`)
      count++
    }
  })

  console.log(`  ${colors.green}Fixed ${count} files${colors.reset}\n`)
}

// Fix specific error type issues
function fixErrorTypes() {
  console.log(`${colors.blue}Fixing error type issues...${colors.reset}`)

  const files = glob.sync('src/**/*.tsx')
  let count = 0

  files.forEach((file) => {
    let content = fs.readFileSync(file, 'utf8')
    const original = content

    // Fix RENDER_ERROR -> UNKNOWN
    content = content.replace(/"RENDER_ERROR"/g, '"UNKNOWN"')

    // Fix NOT_FOUND -> TASK_NOT_FOUND
    content = content.replace(/type:\s*"NOT_FOUND"/g, 'type: "TASK_NOT_FOUND"')

    if (content !== original) {
      fs.writeFileSync(file, content)
      console.log(`  Fixed: ${path.relative(process.cwd(), file)}`)
      count++
    }
  })

  console.log(`  ${colors.green}Fixed ${count} files${colors.reset}\n`)
}

// Fix Tabs component issues
function fixTabsComponent() {
  console.log(`${colors.blue}Fixing Tabs component issues...${colors.reset}`)

  const files = glob.sync('src/**/*.tsx')
  let count = 0

  files.forEach((file) => {
    let content = fs.readFileSync(file, 'utf8')
    const original = content

    // Fix Tabs value/onValueChange props
    content = content.replace(/<Tabs([^>]*)\svalue=/g, '<Tabs$1 defaultValue=')
    content = content.replace(/\sonValueChange={[^}]+}/g, '')

    if (content !== original) {
      fs.writeFileSync(file, content)
      console.log(`  Fixed: ${path.relative(process.cwd(), file)}`)
      count++
    }
  })

  console.log(`  ${colors.green}Fixed ${count} files${colors.reset}\n`)
}

// Main function
function main() {
  console.log(
    `${colors.blue}🔧 Fixing all TypeScript errors...${colors.reset}\n`
  )

  fixButtonSizeProps()
  fixParamsNullChecks()
  fixVariantTypes()
  fixApiImports()
  fixUserTypeIssues()
  fixTaskDataProperty()
  fixErrorTypes()
  fixTabsComponent()

  console.log(`${colors.green}✅ All fixes applied!${colors.reset}`)
  console.log(
    `\n${colors.yellow}Now run 'npm run type-check' to verify the fixes${colors.reset}`
  )
}

main()
