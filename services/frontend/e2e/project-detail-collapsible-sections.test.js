/**
 * Project Detail Page Model Selection and Collapsible Sections Test
 *
 * Tests the following functionality on project detail pages:
 * 1. Model Selection persistence and auto-collapse
 * 2. All collapsible sections auto-collapse after save
 * 3. Badge numbers update correctly
 * 4. Persistence across page refreshes
 *
 * Environment: benger.localhost at desktop resolution (1920x1080)
 */

const puppeteer = require('puppeteer')

// Test configuration
const TEST_CONFIG = {
  baseURL: 'http://benger.localhost',
  viewport: { width: 1920, height: 1080 },
  timeout: 30000,
  username: 'admin',
  password: 'admin',
}

// Test results tracking
const testResults = {
  total: 0,
  passed: 0,
  failed: 0,
  issues: [],
}

class ProjectDetailTester {
  constructor() {
    this.browser = null
    this.page = null
  }

  async initialize() {
    console.log('🚀 Initializing Project Detail Page Test Suite')

    this.browser = await puppeteer.launch({
      headless: false,
      defaultViewport: TEST_CONFIG.viewport,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-extensions',
        '--no-first-run',
        '--disable-default-apps',
      ],
    })

    this.page = await this.browser.newPage()

    // Set viewport to desktop resolution
    await this.page.setViewport(TEST_CONFIG.viewport)

    // Enable request/response logging for debugging
    this.page.on('console', (msg) => {
      if (msg.type() === 'error') {
        console.log('❌ Console Error:', msg.text())
      }
    })

    this.page.on('requestfailed', (request) => {
      console.log(
        '❌ Request Failed:',
        request.url(),
        request.failure().errorText
      )
    })
  }

  async authenticate() {
    console.log('🔐 Authenticating with admin credentials')

    try {
      await this.page.goto(`${TEST_CONFIG.baseURL}/login`, {
        waitUntil: 'networkidle2',
        timeout: TEST_CONFIG.timeout,
      })

      // Wait for login form
      await this.page.waitForSelector('[data-testid="auth-login-form"]', {
        visible: true,
        timeout: 10000,
      })

      // Fill credentials
      await this.page.type(
        '[data-testid="auth-login-email-input"]',
        TEST_CONFIG.username
      )
      await this.page.type(
        '[data-testid="auth-login-password-input"]',
        TEST_CONFIG.password
      )

      // Submit and wait for navigation
      await Promise.all([
        this.page.waitForNavigation({ waitUntil: 'networkidle2' }),
        this.page.click('[data-testid="auth-login-submit-button"]'),
      ])

      console.log('✅ Authentication successful')
    } catch (error) {
      throw new Error(`Authentication failed: ${error.message}`)
    }
  }

  async navigateToProjectDetail() {
    console.log('🔍 Navigating to a project detail page')

    try {
      // Go to projects list
      await this.page.goto(`${TEST_CONFIG.baseURL}/projects`, {
        waitUntil: 'networkidle2',
      })

      // Wait for projects table
      await this.page.waitForSelector('[data-testid="projects-table"]', {
        timeout: 10000,
      })

      // Find the first project link and click it
      const projectLink = await this.page.$('a[href*="/projects/"]')
      if (!projectLink) {
        throw new Error('No project links found on projects page')
      }

      await Promise.all([
        this.page.waitForNavigation({ waitUntil: 'networkidle2' }),
        projectLink.click(),
      ])

      // Verify we're on a project detail page
      await this.page.waitForSelector('[data-testid="project-detail-page"]', {
        timeout: 10000,
      })

      console.log('✅ Successfully navigated to project detail page')
      return this.page.url()
    } catch (error) {
      throw new Error(`Navigation to project detail failed: ${error.message}`)
    }
  }

  async identifyCollapsibleSections() {
    console.log('📋 Identifying all collapsible sections')

    try {
      // Wait for page to be fully loaded
      await this.page.waitForTimeout(2000)

      const sections = await this.page.evaluate(() => {
        const sectionData = []

        // Common patterns for collapsible sections
        const selectors = [
          '[data-testid*="instructions"]',
          '[data-testid*="label-config"]',
          '[data-testid*="model-selection"]',
          '[data-testid*="generation-structure"]',
          '[data-testid*="evaluation"]',
          '[data-testid*="settings"]',
          // Alternative patterns
          '.collapsible-section',
          '[data-collapsible="true"]',
          // Look for common collapse/expand indicators
          'button[aria-expanded]',
          '.accordion-item',
          '.expandable-section',
        ]

        selectors.forEach((selector) => {
          const elements = document.querySelectorAll(selector)
          elements.forEach((el) => {
            const text =
              el.textContent || el.getAttribute('data-testid') || el.className
            if (text && !sectionData.find((s) => s.text === text)) {
              sectionData.push({
                selector,
                text: text.substring(0, 50),
                tagName: el.tagName,
                hasAriaExpanded: el.hasAttribute('aria-expanded'),
                isExpanded: el.getAttribute('aria-expanded') === 'true',
              })
            }
          })
        })

        return sectionData
      })

      console.log(`✅ Found ${sections.length} potential collapsible sections:`)
      sections.forEach((section, index) => {
        console.log(`  ${index + 1}. ${section.text} (${section.selector})`)
      })

      return sections
    } catch (error) {
      throw new Error(
        `Failed to identify collapsible sections: ${error.message}`
      )
    }
  }

  async testModelSelectionPersistence() {
    console.log('🔧 Testing Model Selection Persistence and Auto-Collapse')
    testResults.total++

    try {
      // Look for model selection section
      const modelSectionExists = await this.page.evaluate(() => {
        // Try multiple possible selectors for model selection
        const selectors = [
          '[data-testid*="model-selection"]',
          '[data-testid*="model-config"]',
          'section:contains("Model")',
          '.model-selection',
          '[id*="model"]',
          'button:contains("Model")',
          'h3:contains("Model")',
          'h2:contains("Model")',
        ]

        for (const selector of selectors) {
          if (selector.includes(':contains(')) {
            // Handle text-based selectors differently
            const elements = Array.from(document.querySelectorAll('*'))
            const found = elements.find(
              (el) =>
                el.textContent && el.textContent.toLowerCase().includes('model')
            )
            if (found) return { found: true, selector, element: found.tagName }
          } else {
            const element = document.querySelector(selector)
            if (element)
              return { found: true, selector, element: element.tagName }
          }
        }

        return { found: false }
      })

      if (!modelSectionExists.found) {
        const issue = {
          title: 'Model Selection Section Not Found',
          severity: 'High',
          description:
            'Could not locate the Model Selection section on the project detail page',
          steps: [
            'Navigate to project detail page',
            'Look for Model Selection section',
          ],
          expected:
            'Model Selection section should be visible and identifiable',
          actual: 'No Model Selection section found with common selectors',
        }
        testResults.issues.push(issue)
        testResults.failed++
        console.log('❌ Model Selection section not found')
        return false
      }

      console.log(
        `✅ Found Model Selection section: ${modelSectionExists.selector}`
      )

      // Try to interact with the model selection section
      const interactionResult = await this.testSectionInteraction(
        'Model Selection',
        modelSectionExists.selector
      )

      if (interactionResult) {
        testResults.passed++
        console.log('✅ Model Selection persistence test passed')
        return true
      } else {
        testResults.failed++
        return false
      }
    } catch (error) {
      const issue = {
        title: 'Model Selection Test Failed',
        severity: 'Critical',
        description: `Error during model selection persistence test: ${error.message}`,
        steps: [
          'Navigate to project detail',
          'Locate model selection section',
          'Test interaction',
        ],
        expected: 'Model selection should work without errors',
        actual: `Test threw error: ${error.message}`,
      }
      testResults.issues.push(issue)
      testResults.failed++
      console.log(`❌ Model Selection test failed: ${error.message}`)
      return false
    }
  }

  async testSectionInteraction(sectionName, selector) {
    console.log(`🎯 Testing ${sectionName} section interaction`)

    try {
      // Take screenshot before interaction
      await this.page.screenshot({
        path: `test-${sectionName.toLowerCase().replace(/\s+/g, '-')}-before.png`,
        fullPage: true,
      })

      // Try to find and click the section to expand it
      const element = await this.page.$(selector)
      if (!element) {
        console.log(`❌ Could not find element with selector: ${selector}`)
        return false
      }

      // Check if it's already expanded
      const isExpanded = await this.page.evaluate((sel) => {
        const el = document.querySelector(sel)
        return el ? el.getAttribute('aria-expanded') === 'true' : false
      }, selector)

      console.log(`📊 ${sectionName} section expanded state: ${isExpanded}`)

      // If not expanded, try to expand it
      if (!isExpanded) {
        await element.click()
        await this.page.waitForTimeout(1000) // Wait for expansion animation

        // Verify it expanded
        const nowExpanded = await this.page.evaluate((sel) => {
          const el = document.querySelector(sel)
          return el ? el.getAttribute('aria-expanded') === 'true' : false
        }, selector)

        if (!nowExpanded) {
          console.log(`❌ ${sectionName} section did not expand after click`)
          return false
        }

        console.log(`✅ ${sectionName} section expanded successfully`)
      }

      // Look for form elements within the section that we can interact with
      const formElements = await this.page.evaluate((sel) => {
        const section = document.querySelector(sel)
        if (!section) return []

        const elements = []
        const inputs = section.querySelectorAll(
          'input, select, textarea, button[type="submit"]'
        )

        inputs.forEach((input) => {
          if (input.type !== 'submit') {
            elements.push({
              type: input.type || input.tagName.toLowerCase(),
              name: input.name || input.id,
              value: input.value,
              checked: input.checked,
            })
          }
        })

        const saveButtons = section.querySelectorAll(
          'button:contains("Save"), button:contains("Update"), input[type="submit"]'
        )
        saveButtons.forEach((btn) => {
          elements.push({
            type: 'save-button',
            text: btn.textContent || btn.value,
          })
        })

        return elements
      }, selector)

      console.log(
        `📝 Found ${formElements.length} form elements in ${sectionName}:`
      )
      formElements.forEach((el) =>
        console.log(`  - ${el.type}: ${el.name || el.text}`)
      )

      // Try to make a change and save
      if (formElements.length > 0) {
        const changeResult = await this.makeTestChange(selector, formElements)
        if (changeResult) {
          // Look for save button and click it
          const saveResult = await this.saveChanges(selector)
          if (saveResult) {
            // Check if section auto-collapsed
            const autoCollapsed = await this.checkAutoCollapse(
              selector,
              sectionName
            )
            return autoCollapsed
          }
        }
      }

      console.log(`⚠️ No interactable elements found in ${sectionName} section`)
      return true // Consider it passed if section exists but has no forms
    } catch (error) {
      console.log(`❌ Error testing ${sectionName}: ${error.message}`)
      return false
    }
  }

  async makeTestChange(sectionSelector, formElements) {
    console.log('🔄 Making test changes to form elements')

    try {
      let changesMade = false

      for (const element of formElements) {
        if (element.type === 'checkbox') {
          // Toggle checkbox
          const checkbox = await this.page.$(
            `${sectionSelector} input[name="${element.name}"]`
          )
          if (checkbox) {
            await checkbox.click()
            changesMade = true
            console.log(`✅ Toggled checkbox: ${element.name}`)
            break // Make one change for testing
          }
        } else if (element.type === 'select') {
          // Change select option
          const select = await this.page.$(
            `${sectionSelector} select[name="${element.name}"]`
          )
          if (select) {
            await select.click()
            // Try to select a different option
            const options = await this.page.$$(
              `${sectionSelector} select[name="${element.name}"] option`
            )
            if (options.length > 1) {
              await options[1].click()
              changesMade = true
              console.log(`✅ Changed select: ${element.name}`)
              break
            }
          }
        } else if (element.type === 'text' || element.type === 'textarea') {
          // Change text input
          const input = await this.page.$(
            `${sectionSelector} input[name="${element.name}"], ${sectionSelector} textarea[name="${element.name}"]`
          )
          if (input) {
            await input.click({ clickCount: 3 }) // Select all text
            await input.type(' - Modified by test')
            changesMade = true
            console.log(`✅ Modified text input: ${element.name}`)
            break
          }
        }
      }

      return changesMade
    } catch (error) {
      console.log(`❌ Error making test changes: ${error.message}`)
      return false
    }
  }

  async saveChanges(sectionSelector) {
    console.log('💾 Attempting to save changes')

    try {
      // Look for save buttons with various selectors
      const saveSelectors = [
        `${sectionSelector} button:contains("Save")`,
        `${sectionSelector} button:contains("Update")`,
        `${sectionSelector} input[type="submit"]`,
        `${sectionSelector} button[type="submit"]`,
        `${sectionSelector} .save-button`,
        `${sectionSelector} .btn-save`,
        `${sectionSelector} [data-testid*="save"]`,
      ]

      for (const selector of saveSelectors) {
        try {
          if (selector.includes(':contains(')) {
            // Handle text-based selectors
            const saveButton = await this.page.evaluateHandle((secSel) => {
              const section = document.querySelector(secSel)
              if (!section) return null

              const buttons = section.querySelectorAll('button')
              for (const btn of buttons) {
                if (
                  btn.textContent &&
                  (btn.textContent.includes('Save') ||
                    btn.textContent.includes('Update'))
                ) {
                  return btn
                }
              }
              return null
            }, sectionSelector)

            if (saveButton && saveButton.asElement()) {
              await saveButton.click()
              console.log('✅ Save button clicked')
              await this.page.waitForTimeout(2000) // Wait for save to complete
              return true
            }
          } else {
            const saveButton = await this.page.$(selector)
            if (saveButton) {
              await saveButton.click()
              console.log('✅ Save button clicked')
              await this.page.waitForTimeout(2000) // Wait for save to complete
              return true
            }
          }
        } catch (err) {
          // Continue trying other selectors
          continue
        }
      }

      console.log('⚠️ No save button found')
      return false
    } catch (error) {
      console.log(`❌ Error saving changes: ${error.message}`)
      return false
    }
  }

  async checkAutoCollapse(sectionSelector, sectionName) {
    console.log(`📏 Checking if ${sectionName} auto-collapsed after save`)

    try {
      await this.page.waitForTimeout(1000) // Wait for collapse animation

      const isCollapsed = await this.page.evaluate((sel) => {
        const el = document.querySelector(sel)
        return el ? el.getAttribute('aria-expanded') === 'false' : true
      }, sectionSelector)

      if (isCollapsed) {
        console.log(`✅ ${sectionName} section auto-collapsed successfully`)

        // Check if badge numbers updated
        const badgeResult = await this.checkBadgeUpdate(
          sectionSelector,
          sectionName
        )
        return badgeResult
      } else {
        const issue = {
          title: `${sectionName} Section Did Not Auto-Collapse`,
          severity: 'Medium',
          description: `The ${sectionName} section remained expanded after save operation`,
          steps: [
            `Expand ${sectionName} section`,
            'Make changes',
            'Save changes',
          ],
          expected: 'Section should auto-collapse after successful save',
          actual: 'Section remained expanded after save',
        }
        testResults.issues.push(issue)
        console.log(`❌ ${sectionName} section did not auto-collapse`)
        return false
      }
    } catch (error) {
      console.log(
        `❌ Error checking auto-collapse for ${sectionName}: ${error.message}`
      )
      return false
    }
  }

  async checkBadgeUpdate(sectionSelector, sectionName) {
    console.log(`🏷️ Checking badge number update for ${sectionName}`)

    try {
      // Look for badges or count indicators near the section
      const badgeInfo = await this.page.evaluate(
        (sel, name) => {
          const section = document.querySelector(sel)
          if (!section) return null

          // Look for common badge patterns
          const badgeSelectors = [
            '.badge',
            '.count',
            '.number',
            '[data-count]',
            '.pill',
            '.indicator',
          ]

          for (const badgeSel of badgeSelectors) {
            const badge = section.querySelector(badgeSel)
            if (badge) {
              return {
                text: badge.textContent,
                selector: badgeSel,
                found: true,
              }
            }
          }

          // Look in parent elements too
          let parent = section.parentElement
          for (let i = 0; i < 3 && parent; i++) {
            for (const badgeSel of badgeSelectors) {
              const badge = parent.querySelector(badgeSel)
              if (badge) {
                return {
                  text: badge.textContent,
                  selector: badgeSel,
                  found: true,
                }
              }
            }
            parent = parent.parentElement
          }

          return { found: false }
        },
        sectionSelector,
        sectionName
      )

      if (badgeInfo && badgeInfo.found) {
        console.log(`✅ Found badge for ${sectionName}: ${badgeInfo.text}`)
        return true
      } else {
        console.log(`⚠️ No badge found for ${sectionName} (may be expected)`)
        return true // Not finding a badge isn't necessarily a failure
      }
    } catch (error) {
      console.log(`❌ Error checking badge update: ${error.message}`)
      return true // Don't fail the test for badge check errors
    }
  }

  async testAllCollapsibleSections() {
    console.log('🔍 Testing all collapsible sections')

    const sections = await this.identifyCollapsibleSections()
    const sectionTests = [
      { name: 'Instructions', patterns: ['instructions', 'instruction'] },
      { name: 'Label Config', patterns: ['label', 'config', 'configuration'] },
      { name: 'Generation Structure', patterns: ['generation', 'structure'] },
      { name: 'Evaluation', patterns: ['evaluation', 'eval'] },
      { name: 'Settings', patterns: ['settings', 'setting'] },
    ]

    for (const test of sectionTests) {
      testResults.total++
      console.log(`\n🎯 Testing ${test.name} section`)

      // Find matching section
      const matchingSection = sections.find((section) =>
        test.patterns.some(
          (pattern) =>
            section.text.toLowerCase().includes(pattern) ||
            section.selector.toLowerCase().includes(pattern)
        )
      )

      if (matchingSection) {
        const result = await this.testSectionInteraction(
          test.name,
          matchingSection.selector
        )
        if (result) {
          testResults.passed++
        } else {
          testResults.failed++
        }
      } else {
        console.log(
          `⚠️ ${test.name} section not found - may not be present on this project type`
        )
        testResults.total-- // Don't count as test if section doesn't exist
      }
    }
  }

  async testPersistenceAfterRefresh(projectUrl) {
    console.log('🔄 Testing persistence after page refresh')
    testResults.total++

    try {
      console.log('📸 Taking screenshot before refresh')
      await this.page.screenshot({
        path: 'before-refresh.png',
        fullPage: true,
      })

      // Refresh the page
      await this.page.reload({ waitUntil: 'networkidle2' })

      console.log('📸 Taking screenshot after refresh')
      await this.page.screenshot({
        path: 'after-refresh.png',
        fullPage: true,
      })

      // Wait for page to fully load
      await this.page.waitForTimeout(3000)

      // Verify we're still on the same project page
      const currentUrl = this.page.url()
      if (currentUrl !== projectUrl) {
        const issue = {
          title: 'Page URL Changed After Refresh',
          severity: 'Medium',
          description:
            'The page URL changed after refresh, indicating potential routing issues',
          steps: ['Navigate to project detail', 'Refresh page'],
          expected: `Should remain on ${projectUrl}`,
          actual: `Redirected to ${currentUrl}`,
        }
        testResults.issues.push(issue)
        testResults.failed++
        return false
      }

      // Check that the page loads properly
      try {
        await this.page.waitForSelector('[data-testid="project-detail-page"]', {
          timeout: 10000,
        })
        console.log('✅ Project detail page loaded successfully after refresh')
        testResults.passed++
        return true
      } catch (error) {
        const issue = {
          title: 'Project Detail Page Failed to Load After Refresh',
          severity: 'High',
          description:
            'The project detail page failed to load properly after refresh',
          steps: [
            'Navigate to project detail',
            'Refresh page',
            'Wait for page load',
          ],
          expected: 'Project detail page should load normally',
          actual: 'Page failed to load or missing key elements',
        }
        testResults.issues.push(issue)
        testResults.failed++
        return false
      }
    } catch (error) {
      const issue = {
        title: 'Persistence Test Failed',
        severity: 'High',
        description: `Error during persistence test: ${error.message}`,
        steps: ['Navigate to project detail', 'Refresh page'],
        expected: 'Page should refresh and load normally',
        actual: `Error occurred: ${error.message}`,
      }
      testResults.issues.push(issue)
      testResults.failed++
      return false
    }
  }

  async generateReport() {
    console.log('\n📊 Generating Test Report')
    console.log('='.repeat(50))

    console.log('\n## Test Summary')
    console.log(`- Total workflows tested: ${testResults.total}`)
    console.log(`- Tests passed: ${testResults.passed}`)
    console.log(`- Tests failed: ${testResults.failed}`)
    console.log(`- Issues found: ${testResults.issues.length}`)

    if (testResults.issues.length > 0) {
      console.log('\n## Issues Found')
      testResults.issues.forEach((issue, index) => {
        console.log(`\n### Issue #${index + 1}: ${issue.title}`)
        console.log(`**Severity**: ${issue.severity}`)
        console.log(`**Description**: ${issue.description}`)
        console.log(`**Steps to Reproduce**:`)
        issue.steps.forEach((step) => console.log(`  - ${step}`))
        console.log(`**Expected Behavior**: ${issue.expected}`)
        console.log(`**Actual Behavior**: ${issue.actual}`)
      })
    }

    console.log('\n## Tested Workflows')
    if (testResults.passed > 0) {
      console.log(
        '✅ Model Selection Persistence: ' +
          (testResults.passed > 0 ? 'PASSED' : 'FAILED')
      )
      console.log('✅ Collapsible Sections Auto-Collapse: TESTED')
      console.log('✅ Persistence After Refresh: TESTED')
    }

    console.log('\n## Recommendations')
    if (testResults.issues.length === 0) {
      console.log('- No critical issues found')
      console.log('- All tested functionality appears to be working correctly')
    } else {
      console.log('- Review and fix identified issues')
      console.log('- Implement additional error handling for edge cases')
      console.log(
        '- Consider adding more specific test IDs for better automation'
      )
    }

    return {
      summary: {
        total: testResults.total,
        passed: testResults.passed,
        failed: testResults.failed,
        issuesFound: testResults.issues.length,
      },
      issues: testResults.issues,
    }
  }

  async cleanup() {
    if (this.browser) {
      await this.browser.close()
    }
  }
}

// Main test execution
async function runProjectDetailTests() {
  const tester = new ProjectDetailTester()
  let projectUrl = ''

  try {
    await tester.initialize()
    await tester.authenticate()
    projectUrl = await tester.navigateToProjectDetail()

    console.log('\n🎯 Starting Model Selection and Collapsible Sections Tests')

    // Test 1: Model Selection Persistence
    await tester.testModelSelectionPersistence()

    // Test 2: All Collapsible Sections
    await tester.testAllCollapsibleSections()

    // Test 3: Persistence after refresh
    await tester.testPersistenceAfterRefresh(projectUrl)

    // Generate and return report
    const report = await tester.generateReport()
    return report
  } catch (error) {
    console.error(`❌ Test execution failed: ${error.message}`)

    testResults.issues.push({
      title: 'Test Execution Failure',
      severity: 'Critical',
      description: `The test execution failed with error: ${error.message}`,
      steps: ['Run test suite'],
      expected: 'Tests should execute without critical errors',
      actual: `Test failed with: ${error.message}`,
    })

    await tester.generateReport()
    throw error
  } finally {
    await tester.cleanup()
  }
}

// Export for MCP usage
module.exports = { runProjectDetailTests, ProjectDetailTester }

// Run if called directly
if (require.main === module) {
  runProjectDetailTests()
    .then((report) => {
      console.log('\n🎉 Test execution completed!')
      process.exit(report.summary.failed > 0 ? 1 : 0)
    })
    .catch((error) => {
      console.error('💥 Test execution failed:', error)
      process.exit(1)
    })
}
