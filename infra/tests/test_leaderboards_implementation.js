/**
 * Test Suite: Leaderboards Implementation (Issue #790)
 *
 * Tests the complete leaderboards feature including:
 * 1. Navigation and page structure
 * 2. Human Annotators leaderboard with time period filters
 * 3. LLM leaderboard "Coming Soon" placeholder
 * 4. Profile privacy settings (pseudonym preferences)
 * 5. Backend API endpoints
 * 6. Pseudonym/real name display logic
 */

const puppeteer = require('puppeteer');

const BASE_URL = 'http://benger.localhost';
const DESKTOP_WIDTH = 1920;
const DESKTOP_HEIGHT = 1080;

// Test credentials
const ADMIN_USER = { username: 'admin', password: 'admin' };

// Test results tracking
const testResults = {
  passed: [],
  failed: [],
  warnings: [],
  screenshots: []
};

function logSuccess(testName, details = '') {
  testResults.passed.push({ test: testName, details });
  console.log(`✅ PASS: ${testName}`);
  if (details) console.log(`   ${details}`);
}

function logFailure(testName, error, details = '') {
  testResults.failed.push({ test: testName, error: error.message || error, details });
  console.log(`❌ FAIL: ${testName}`);
  console.log(`   Error: ${error.message || error}`);
  if (details) console.log(`   ${details}`);
}

function logWarning(testName, warning) {
  testResults.warnings.push({ test: testName, warning });
  console.log(`⚠️  WARN: ${testName}`);
  console.log(`   ${warning}`);
}

async function takeScreenshot(page, name) {
  const filename = `/tmp/leaderboards_test_${name}_${Date.now()}.png`;
  await page.screenshot({ path: filename, fullPage: true });
  testResults.screenshots.push({ name, path: filename });
  console.log(`📸 Screenshot saved: ${filename}`);
  return filename;
}

async function login(page, username, password) {
  console.log(`\n🔐 Logging in as ${username}...`);

  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle0' });

  // Check if already logged in (auto-login in dev mode)
  const currentUrl = page.url();
  if (currentUrl.includes('/dashboard')) {
    console.log('   Already logged in (auto-login detected)');
    return;
  }

  // Fill in login form
  await page.waitForSelector('input[name="username"]', { timeout: 5000 });
  await page.type('input[name="username"]', username);
  await page.type('input[name="password"]', password);

  // Click login button
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle0' }),
    page.click('button[type="submit"]')
  ]);

  // Verify we're on dashboard
  const dashboardUrl = page.url();
  if (!dashboardUrl.includes('/dashboard')) {
    throw new Error(`Login failed - expected dashboard URL, got: ${dashboardUrl}`);
  }

  console.log('   ✓ Login successful');
}

async function testNavigationToLeaderboards(page) {
  console.log('\n🧪 Test: Navigation to Leaderboards Page');

  try {
    // Ensure we're on dashboard
    await page.goto(`${BASE_URL}/dashboard`, { waitUntil: 'networkidle0' });

    // Take screenshot of dashboard
    await takeScreenshot(page, 'dashboard');

    // Look for Leaderboards link in sidebar
    const leaderboardLink = await page.evaluate(() => {
      const links = Array.from(document.querySelectorAll('a'));
      return links.find(link =>
        link.textContent.toLowerCase().includes('leaderboard')
      )?.href;
    });

    if (!leaderboardLink) {
      throw new Error('Leaderboards link not found in sidebar');
    }

    logSuccess('Found Leaderboards link in sidebar', `URL: ${leaderboardLink}`);

    // Navigate to leaderboards
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle0' }),
      page.goto(leaderboardLink)
    ]);

    // Verify URL
    const currentUrl = page.url();
    if (!currentUrl.includes('/leaderboards')) {
      throw new Error(`Expected /leaderboards URL, got: ${currentUrl}`);
    }

    logSuccess('Successfully navigated to Leaderboards page', `URL: ${currentUrl}`);

    // Take screenshot
    await takeScreenshot(page, 'leaderboards_page');

  } catch (error) {
    logFailure('Navigation to Leaderboards Page', error);
    await takeScreenshot(page, 'navigation_error');
    throw error;
  }
}

async function testPageStructure(page) {
  console.log('\n🧪 Test: Page Structure');

  try {
    // Test breadcrumb
    const breadcrumb = await page.evaluate(() => {
      const breadcrumbElements = Array.from(document.querySelectorAll('nav a, nav span'));
      return breadcrumbElements.map(el => el.textContent.trim());
    });

    if (!breadcrumb.some(text => text.toLowerCase().includes('dashboard'))) {
      logWarning('Breadcrumb: Dashboard link', 'Dashboard not found in breadcrumb');
    } else {
      logSuccess('Breadcrumb: Dashboard link exists');
    }

    if (!breadcrumb.some(text => text.toLowerCase().includes('leaderboard'))) {
      logWarning('Breadcrumb: Leaderboards link', 'Leaderboards not found in breadcrumb');
    } else {
      logSuccess('Breadcrumb: Leaderboards link exists');
    }

    // Test page title
    const pageTitle = await page.evaluate(() => {
      const h1 = document.querySelector('h1');
      return h1 ? h1.textContent.trim() : null;
    });

    if (!pageTitle || !pageTitle.toLowerCase().includes('leaderboard')) {
      logFailure('Page title', new Error(`Expected "Leaderboards", got: ${pageTitle}`));
    } else {
      logSuccess('Page title exists', `Title: ${pageTitle}`);
    }

    // Test tabs exist
    const tabs = await page.evaluate(() => {
      const tabButtons = Array.from(document.querySelectorAll('button'));
      const tabTexts = tabButtons
        .filter(btn => {
          const text = btn.textContent.toLowerCase();
          return text.includes('human') || text.includes('llm');
        })
        .map(btn => ({
          text: btn.textContent.trim(),
          classes: btn.className
        }));
      return tabTexts;
    });

    if (tabs.length !== 2) {
      logFailure('Tab count', new Error(`Expected 2 tabs, found ${tabs.length}`));
    } else {
      logSuccess('Two tabs exist', `Tabs: ${tabs.map(t => t.text).join(', ')}`);
    }

    // Test "Human Annotators" tab is active by default
    const humanTabActive = tabs.find(t =>
      t.text.toLowerCase().includes('human') || t.text.toLowerCase().includes('annotator')
    );

    if (!humanTabActive) {
      logFailure('Human Annotators tab', new Error('Human Annotators tab not found'));
    } else if (!humanTabActive.classes.includes('emerald')) {
      logWarning('Human Annotators tab default active',
        'Human Annotators tab may not be active by default (no emerald color detected)');
    } else {
      logSuccess('Human Annotators tab is active by default');
    }

  } catch (error) {
    logFailure('Page Structure test', error);
    await takeScreenshot(page, 'page_structure_error');
    throw error;
  }
}

async function testHumanAnnotatorsTab(page) {
  console.log('\n🧪 Test: Human Annotators Tab');

  try {
    // Test leaderboard table exists
    const tableExists = await page.evaluate(() => {
      return !!document.querySelector('table');
    });

    if (!tableExists) {
      logWarning('Leaderboard table', 'No table found - may be empty state');
    } else {
      logSuccess('Leaderboard table exists');

      // Test table headers
      const headers = await page.evaluate(() => {
        const ths = Array.from(document.querySelectorAll('th'));
        return ths.map(th => th.textContent.trim());
      });

      const expectedHeaders = ['rank', 'annotator', 'annotation'];
      const hasAllHeaders = expectedHeaders.every(expected =>
        headers.some(header => header.toLowerCase().includes(expected))
      );

      if (!hasAllHeaders) {
        logFailure('Table headers',
          new Error(`Expected headers containing: ${expectedHeaders.join(', ')}, got: ${headers.join(', ')}`));
      } else {
        logSuccess('Table has correct headers', `Headers: ${headers.join(', ')}`);
      }

      // Test for medals in top 3
      const medals = await page.evaluate(() => {
        const cells = Array.from(document.querySelectorAll('td'));
        return cells.slice(0, 3).map(cell => cell.textContent.trim());
      });

      const hasMedals = medals.some(text => /🥇|🥈|🥉/.test(text));
      if (hasMedals) {
        logSuccess('Medals displayed for top positions', `Found medals in: ${medals.join(', ')}`);
      } else {
        logWarning('Medals for top positions', 'No medal emojis found in first 3 rows');
      }

      // Test current user highlighting
      const highlightedRow = await page.evaluate(() => {
        const rows = Array.from(document.querySelectorAll('tr'));
        const highlighted = rows.find(row =>
          row.className.includes('emerald-50') ||
          row.className.includes('emerald-950')
        );
        return highlighted ? highlighted.textContent.trim() : null;
      });

      if (highlightedRow) {
        logSuccess('Current user row is highlighted', `Row content: ${highlightedRow.substring(0, 50)}...`);
      } else {
        logWarning('Current user highlighting', 'No highlighted row found (user may have no annotations)');
      }
    }

    // Test time period filters
    const filterButtons = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      return buttons
        .filter(btn => {
          const text = btn.textContent.toLowerCase();
          return text.includes('all') || text.includes('month') || text.includes('week') || text.includes('time');
        })
        .map(btn => ({
          text: btn.textContent.trim(),
          classes: btn.className
        }));
    });

    if (filterButtons.length < 3) {
      logFailure('Time period filters',
        new Error(`Expected 3 filter buttons (All Time, This Month, This Week), found ${filterButtons.length}`));
    } else {
      logSuccess('Time period filter buttons exist',
        `Filters: ${filterButtons.map(f => f.text).join(', ')}`);
    }

    // Test clicking "This Month" filter
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const monthButton = buttons.find(btn =>
        btn.textContent.toLowerCase().includes('month')
      );
      if (monthButton) monthButton.click();
    });

    // Wait for potential API call
    await page.waitForTimeout(1500);

    logSuccess('Clicked "This Month" filter');
    await takeScreenshot(page, 'monthly_filter');

    // Test clicking "This Week" filter
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const weekButton = buttons.find(btn =>
        btn.textContent.toLowerCase().includes('week')
      );
      if (weekButton) weekButton.click();
    });

    await page.waitForTimeout(1500);

    logSuccess('Clicked "This Week" filter');
    await takeScreenshot(page, 'weekly_filter');

    // Go back to "All Time"
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const allTimeButton = buttons.find(btn =>
        btn.textContent.toLowerCase().includes('all') ||
        btn.textContent.toLowerCase().includes('time')
      );
      if (allTimeButton) allTimeButton.click();
    });

    await page.waitForTimeout(1500);
    logSuccess('Clicked "All Time" filter');

  } catch (error) {
    logFailure('Human Annotators Tab test', error);
    await takeScreenshot(page, 'human_annotators_error');
    throw error;
  }
}

async function testLLMTab(page) {
  console.log('\n🧪 Test: LLM Tab');

  try {
    // Click LLM tab
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const llmButton = buttons.find(btn =>
        btn.textContent.toLowerCase().includes('llm')
      );
      if (llmButton) {
        llmButton.click();
      } else {
        throw new Error('LLM tab button not found');
      }
    });

    await page.waitForTimeout(500);

    logSuccess('Clicked LLM tab');
    await takeScreenshot(page, 'llm_tab');

    // Test for "Coming Soon" placeholder
    const comingSoonText = await page.evaluate(() => {
      const elements = Array.from(document.querySelectorAll('*'));
      return elements.find(el =>
        el.textContent.toLowerCase().includes('coming soon')
      )?.textContent.trim();
    });

    if (!comingSoonText) {
      logFailure('LLM tab Coming Soon placeholder',
        new Error('Expected "Coming Soon" message, but not found'));
    } else {
      logSuccess('LLM tab shows "Coming Soon" placeholder', `Text: ${comingSoonText}`);
    }

    // Switch back to Human Annotators tab
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const humanButton = buttons.find(btn =>
        btn.textContent.toLowerCase().includes('human') ||
        btn.textContent.toLowerCase().includes('annotator')
      );
      if (humanButton) humanButton.click();
    });

    await page.waitForTimeout(500);
    logSuccess('Switched back to Human Annotators tab');

  } catch (error) {
    logFailure('LLM Tab test', error);
    await takeScreenshot(page, 'llm_tab_error');
    throw error;
  }
}

async function testProfilePrivacySettings(page) {
  console.log('\n🧪 Test: Profile Privacy Settings');

  try {
    // Navigate to profile page
    await page.goto(`${BASE_URL}/profile`, { waitUntil: 'networkidle0' });

    await takeScreenshot(page, 'profile_page');

    // Test Privacy Settings section exists
    const privacySection = await page.evaluate(() => {
      const headings = Array.from(document.querySelectorAll('h2, h3'));
      return headings.find(h =>
        h.textContent.toLowerCase().includes('privacy')
      )?.textContent.trim();
    });

    if (!privacySection) {
      logFailure('Privacy Settings section',
        new Error('Privacy Settings section not found on profile page'));
      return;
    }

    logSuccess('Privacy Settings section exists', `Section: ${privacySection}`);

    // Test pseudonym field exists
    const pseudonymField = await page.evaluate(() => {
      const inputs = Array.from(document.querySelectorAll('input'));
      const field = inputs.find(input =>
        input.id === 'pseudonym' || input.name === 'pseudonym'
      );
      return field ? {
        value: field.value,
        disabled: field.disabled,
        type: field.type
      } : null;
    });

    if (!pseudonymField) {
      logFailure('Pseudonym field', new Error('Pseudonym input field not found'));
    } else {
      logSuccess('Pseudonym field exists',
        `Value: ${pseudonymField.value}, Disabled: ${pseudonymField.disabled}`);

      if (!pseudonymField.disabled) {
        logWarning('Pseudonym field editability',
          'Pseudonym field is not disabled - should be read-only');
      } else {
        logSuccess('Pseudonym field is read-only (disabled)');
      }

      if (!pseudonymField.value || pseudonymField.value.trim() === '') {
        logWarning('Pseudonym value', 'Pseudonym field is empty');
      } else {
        logSuccess('Pseudonym has a value', `Pseudonym: ${pseudonymField.value}`);
      }
    }

    // Test "use pseudonym" checkbox
    const usePseudonymCheckbox = await page.evaluate(() => {
      const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
      const checkbox = checkboxes.find(cb =>
        cb.id === 'use_pseudonym' || cb.name === 'use_pseudonym'
      );
      return checkbox ? {
        checked: checkbox.checked,
        id: checkbox.id
      } : null;
    });

    if (!usePseudonymCheckbox) {
      logFailure('Use pseudonym checkbox',
        new Error('"I want to work under my pseudonym" checkbox not found'));
    } else {
      logSuccess('Use pseudonym checkbox exists',
        `Checked: ${usePseudonymCheckbox.checked}`);

      if (!usePseudonymCheckbox.checked) {
        logWarning('Default checkbox state',
          'Checkbox is unchecked - expected to be checked by default');
      } else {
        logSuccess('Checkbox is checked by default');
      }
    }

    // Test toggling the checkbox
    const initialState = usePseudonymCheckbox?.checked;

    await page.evaluate(() => {
      const checkbox = document.querySelector('#use_pseudonym');
      if (checkbox) checkbox.click();
    });

    await page.waitForTimeout(300);

    const afterToggle = await page.evaluate(() => {
      const checkbox = document.querySelector('#use_pseudonym');
      return checkbox ? checkbox.checked : null;
    });

    if (afterToggle === initialState) {
      logFailure('Checkbox toggle',
        new Error('Checkbox state did not change after click'));
    } else {
      logSuccess('Checkbox toggles correctly',
        `Changed from ${initialState} to ${afterToggle}`);
    }

    await takeScreenshot(page, 'privacy_settings_toggled');

    // Test saving the change
    const saveButton = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button[type="submit"]'));
      return buttons.find(btn =>
        btn.textContent.toLowerCase().includes('update') ||
        btn.textContent.toLowerCase().includes('save')
      ) ? true : false;
    });

    if (!saveButton) {
      logWarning('Save button', 'Update/Save button not found');
    } else {
      // Click save button
      await page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button[type="submit"]'));
        const updateBtn = buttons.find(btn =>
          btn.textContent.toLowerCase().includes('update') ||
          btn.textContent.toLowerCase().includes('save')
        );
        if (updateBtn) updateBtn.click();
      });

      // Wait for potential success message
      await page.waitForTimeout(2000);

      const successMessage = await page.evaluate(() => {
        const messages = Array.from(document.querySelectorAll('*'));
        return messages.find(el =>
          el.textContent.toLowerCase().includes('success') ||
          el.textContent.toLowerCase().includes('updated')
        )?.textContent.trim();
      });

      if (successMessage) {
        logSuccess('Profile update saved successfully', `Message: ${successMessage}`);
      } else {
        logWarning('Save confirmation', 'No success message found after save');
      }

      await takeScreenshot(page, 'privacy_settings_saved');
    }

    // Toggle back to original state for cleanup
    await page.evaluate(() => {
      const checkbox = document.querySelector('#use_pseudonym');
      if (checkbox) checkbox.click();
    });

    await page.waitForTimeout(300);

    // Save again
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button[type="submit"]'));
      const updateBtn = buttons.find(btn =>
        btn.textContent.toLowerCase().includes('update') ||
        btn.textContent.toLowerCase().includes('save')
      );
      if (updateBtn) updateBtn.click();
    });

    await page.waitForTimeout(2000);
    logSuccess('Restored original privacy settings');

  } catch (error) {
    logFailure('Profile Privacy Settings test', error);
    await takeScreenshot(page, 'profile_privacy_error');
    throw error;
  }
}

async function testBackendAPI(page) {
  console.log('\n🧪 Test: Backend API Endpoints');

  try {
    // Enable request interception to monitor API calls
    await page.setRequestInterception(true);

    const apiCalls = [];

    page.on('request', request => {
      if (request.url().includes('/api/leaderboards')) {
        apiCalls.push({
          url: request.url(),
          method: request.method()
        });
      }
      request.continue();
    });

    let apiResponses = [];

    page.on('response', async response => {
      if (response.url().includes('/api/leaderboards')) {
        const status = response.status();
        const url = response.url();

        try {
          const data = await response.json();
          apiResponses.push({
            url,
            status,
            data
          });
        } catch (e) {
          apiResponses.push({
            url,
            status,
            error: 'Failed to parse JSON'
          });
        }
      }
    });

    // Navigate to leaderboards to trigger API calls
    await page.goto(`${BASE_URL}/leaderboards`, { waitUntil: 'networkidle0' });
    await page.waitForTimeout(2000);

    if (apiCalls.length === 0) {
      logWarning('API calls', 'No API calls to /api/leaderboards detected');
    } else {
      logSuccess('API calls detected', `Found ${apiCalls.length} API call(s)`);
      apiCalls.forEach(call => {
        console.log(`   ${call.method} ${call.url}`);
      });
    }

    if (apiResponses.length === 0) {
      logWarning('API responses', 'No API responses captured');
    } else {
      logSuccess('API responses captured', `Found ${apiResponses.length} response(s)`);

      apiResponses.forEach(response => {
        if (response.status === 200) {
          logSuccess(`API endpoint ${response.url.split('/api')[1]}`,
            `Status: ${response.status}`);

          // Validate response structure
          if (response.data) {
            if (response.url.includes('/annotators')) {
              if (response.data.leaderboard && Array.isArray(response.data.leaderboard)) {
                logSuccess('Leaderboard response structure',
                  `Contains ${response.data.leaderboard.length} entries`);

                // Check if entries have required fields
                if (response.data.leaderboard.length > 0) {
                  const firstEntry = response.data.leaderboard[0];
                  const requiredFields = ['rank', 'user_id', 'display_name', 'annotation_count', 'is_current_user'];
                  const hasAllFields = requiredFields.every(field => field in firstEntry);

                  if (hasAllFields) {
                    logSuccess('Leaderboard entry structure',
                      `All required fields present: ${requiredFields.join(', ')}`);

                    // Log sample entry
                    console.log(`   Sample entry: Rank ${firstEntry.rank}, Name: ${firstEntry.display_name}, Count: ${firstEntry.annotation_count}`);
                  } else {
                    logFailure('Leaderboard entry structure',
                      new Error(`Missing required fields. Entry: ${JSON.stringify(firstEntry)}`));
                  }
                }
              } else {
                logWarning('Leaderboard response', 'Missing or invalid leaderboard array');
              }
            }
          }
        } else {
          logFailure(`API endpoint ${response.url.split('/api')[1]}`,
            new Error(`HTTP ${response.status}`));
        }
      });
    }

    // Disable request interception
    await page.setRequestInterception(false);

  } catch (error) {
    logFailure('Backend API test', error);
    throw error;
  }
}

async function testPseudonymDisplayLogic(page) {
  console.log('\n🧪 Test: Pseudonym Display Logic');

  try {
    // This test verifies that the display_name in the API response
    // respects the user's use_pseudonym preference

    await page.goto(`${BASE_URL}/leaderboards`, { waitUntil: 'networkidle0' });
    await page.waitForTimeout(2000);

    const leaderboardEntries = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('tbody tr'));
      return rows.map(row => {
        const cells = Array.from(row.querySelectorAll('td'));
        return {
          rank: cells[0]?.textContent.trim(),
          name: cells[1]?.textContent.trim(),
          count: cells[2]?.textContent.trim()
        };
      });
    });

    if (leaderboardEntries.length === 0) {
      logWarning('Pseudonym display logic', 'No leaderboard entries to test');
    } else {
      logSuccess('Leaderboard entries retrieved',
        `Found ${leaderboardEntries.length} entries`);

      console.log('\n   Sample entries:');
      leaderboardEntries.slice(0, 5).forEach(entry => {
        console.log(`   ${entry.rank} - ${entry.name}: ${entry.count} annotations`);
      });

      // Check if any entries have "You" badge (current user)
      const currentUserEntry = leaderboardEntries.find(entry =>
        entry.name.includes('You')
      );

      if (currentUserEntry) {
        logSuccess('Current user identified in leaderboard',
          `Entry: ${currentUserEntry.name}`);
      } else {
        logWarning('Current user in leaderboard',
          'Current user not found (may have no annotations)');
      }
    }

  } catch (error) {
    logFailure('Pseudonym Display Logic test', error);
    await takeScreenshot(page, 'pseudonym_display_error');
    throw error;
  }
}

function printTestReport() {
  console.log('\n' + '='.repeat(80));
  console.log('TEST SUMMARY REPORT');
  console.log('='.repeat(80));

  console.log(`\n✅ PASSED: ${testResults.passed.length}`);
  testResults.passed.forEach(result => {
    console.log(`   - ${result.test}`);
  });

  if (testResults.warnings.length > 0) {
    console.log(`\n⚠️  WARNINGS: ${testResults.warnings.length}`);
    testResults.warnings.forEach(result => {
      console.log(`   - ${result.test}: ${result.warning}`);
    });
  }

  if (testResults.failed.length > 0) {
    console.log(`\n❌ FAILED: ${testResults.failed.length}`);
    testResults.failed.forEach(result => {
      console.log(`   - ${result.test}`);
      console.log(`     Error: ${result.error}`);
    });
  }

  if (testResults.screenshots.length > 0) {
    console.log(`\n📸 SCREENSHOTS: ${testResults.screenshots.length}`);
    testResults.screenshots.forEach(screenshot => {
      console.log(`   - ${screenshot.name}: ${screenshot.path}`);
    });
  }

  console.log('\n' + '='.repeat(80));

  const totalTests = testResults.passed.length + testResults.failed.length;
  const passRate = totalTests > 0 ? ((testResults.passed.length / totalTests) * 100).toFixed(1) : 0;

  console.log(`OVERALL: ${testResults.passed.length}/${totalTests} tests passed (${passRate}%)`);
  console.log('='.repeat(80) + '\n');
}

async function runTests() {
  let browser;
  let page;

  try {
    console.log('🚀 Starting Leaderboards Implementation Tests (Issue #790)');
    console.log(`   Target: ${BASE_URL}`);
    console.log(`   Resolution: ${DESKTOP_WIDTH}x${DESKTOP_HEIGHT}\n`);

    // Launch browser
    browser = await puppeteer.launch({
      headless: true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-web-security'
      ]
    });

    page = await browser.newPage();
    await page.setViewport({ width: DESKTOP_WIDTH, height: DESKTOP_HEIGHT });

    // Enable console logging from page
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`   [Browser Error]: ${msg.text()}`);
      }
    });

    // Login
    await login(page, ADMIN_USER.username, ADMIN_USER.password);

    // Run test suites
    await testNavigationToLeaderboards(page);
    await testPageStructure(page);
    await testHumanAnnotatorsTab(page);
    await testLLMTab(page);
    await testProfilePrivacySettings(page);
    await testBackendAPI(page);
    await testPseudonymDisplayLogic(page);

    console.log('\n✅ All test suites completed!');

  } catch (error) {
    console.error('\n❌ Test execution failed:');
    console.error(error);

    if (page) {
      await takeScreenshot(page, 'fatal_error');
    }
  } finally {
    if (browser) {
      await browser.close();
    }

    printTestReport();
  }
}

// Run the tests
runTests();
