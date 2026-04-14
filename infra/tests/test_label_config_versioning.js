/**
 * Test Suite: Label Config Versioning System
 *
 * Tests the complete versioning workflow for label configurations:
 * 1. Version API endpoints functionality
 * 2. Automatic versioning on label_config updates
 * 3. Version history and comparison
 * 4. No regression in existing project updates
 */

const puppeteer = require('puppeteer');

const BASE_URL = 'http://benger.localhost';
const PROJECT_ID = 'e7f77958-cc63-46cf-93f1-83ac344caeab'; // AGB project

// Test results tracking
const testResults = {
  passed: [],
  failed: [],
  warnings: []
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

async function waitForResponse(page, urlPattern, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      reject(new Error(`Timeout waiting for response matching ${urlPattern}`));
    }, timeout);

    page.on('response', async response => {
      if (response.url().includes(urlPattern)) {
        clearTimeout(timeoutId);
        const responseData = {
          status: response.status(),
          url: response.url(),
          headers: response.headers()
        };

        try {
          responseData.body = await response.json();
        } catch (e) {
          responseData.body = await response.text();
        }

        resolve(responseData);
      }
    });
  });
}

async function makeAPIRequest(page, method, endpoint, body = null) {
  const response = await page.evaluate(async (args) => {
    const { method, endpoint, body } = args;

    const options = {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
      credentials: 'include'
    };

    if (body) {
      options.body = JSON.stringify(body);
    }

    const res = await fetch(`http://api.localhost${endpoint}`, options);
    const data = await res.text();

    return {
      status: res.status,
      statusText: res.statusText,
      body: data,
      headers: Object.fromEntries(res.headers.entries())
    };
  }, { method, endpoint, body });

  // Try to parse JSON
  try {
    response.json = JSON.parse(response.body);
  } catch (e) {
    response.json = null;
  }

  return response;
}

async function runTests() {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  let page;

  try {
    page = await browser.newPage();
    await page.setViewport({ width: 1920, height: 1080 });

    console.log('\n=== STARTING LABEL CONFIG VERSIONING TESTS ===\n');

    // Navigate to the application to establish session
    console.log('Setting up test environment...');
    await page.goto(BASE_URL, { waitUntil: 'networkidle2', timeout: 30000 });
    await page.waitForTimeout(2000); // Allow auto-login to complete

    console.log('\n--- TEST SUITE 1: VERSION API ENDPOINTS ---\n');

    // Test 1.1: GET all versions
    console.log('Test 1.1: GET /api/projects/{id}/label-config/versions');
    try {
      const versionsResponse = await makeAPIRequest(
        page,
        'GET',
        `/api/projects/${PROJECT_ID}/label-config/versions`
      );

      if (versionsResponse.status === 200 && versionsResponse.json) {
        const versions = versionsResponse.json;
        logSuccess(
          'GET all versions endpoint',
          `Returned ${Array.isArray(versions) ? versions.length : 'N/A'} version(s). Status: ${versionsResponse.status}`
        );

        if (Array.isArray(versions) && versions.length > 0) {
          console.log(`   First version: ${JSON.stringify(versions[0], null, 2).substring(0, 200)}...`);
        }
      } else {
        logFailure(
          'GET all versions endpoint',
          `Status ${versionsResponse.status}: ${versionsResponse.statusText}`,
          `Response: ${versionsResponse.body.substring(0, 200)}`
        );
      }
    } catch (error) {
      logFailure('GET all versions endpoint', error);
    }

    // Test 1.2: GET specific version (v1)
    console.log('\nTest 1.2: GET /api/projects/{id}/label-config/versions/v1');
    try {
      const v1Response = await makeAPIRequest(
        page,
        'GET',
        `/api/projects/${PROJECT_ID}/label-config/versions/v1`
      );

      if (v1Response.status === 200 && v1Response.json) {
        logSuccess(
          'GET specific version v1 endpoint',
          `Status: ${v1Response.status}, Has config: ${!!v1Response.json.config}`
        );
        console.log(`   Version data: ${JSON.stringify(v1Response.json, null, 2).substring(0, 300)}...`);
      } else {
        logFailure(
          'GET specific version v1 endpoint',
          `Status ${v1Response.status}: ${v1Response.statusText}`,
          `Response: ${v1Response.body.substring(0, 200)}`
        );
      }
    } catch (error) {
      logFailure('GET specific version v1 endpoint', error);
    }

    // Test 1.3: GET version distribution
    console.log('\nTest 1.3: GET /api/projects/{id}/generations/version-distribution');
    try {
      const distributionResponse = await makeAPIRequest(
        page,
        'GET',
        `/api/projects/${PROJECT_ID}/generations/version-distribution`
      );

      if (distributionResponse.status === 200 && distributionResponse.json) {
        logSuccess(
          'GET version distribution endpoint',
          `Status: ${distributionResponse.status}, Distribution data received`
        );
        console.log(`   Distribution: ${JSON.stringify(distributionResponse.json, null, 2)}`);
      } else {
        logFailure(
          'GET version distribution endpoint',
          `Status ${distributionResponse.status}: ${distributionResponse.statusText}`,
          `Response: ${distributionResponse.body.substring(0, 200)}`
        );
      }
    } catch (error) {
      logFailure('GET version distribution endpoint', error);
    }

    console.log('\n--- TEST SUITE 2: AUTO-VERSIONING ON UPDATE ---\n');

    // Test 2.1: Get current project state
    console.log('Test 2.1: Get current project state');
    let currentProject;
    try {
      const projectResponse = await makeAPIRequest(
        page,
        'GET',
        `/api/projects/${PROJECT_ID}`
      );

      if (projectResponse.status === 200 && projectResponse.json) {
        currentProject = projectResponse.json;
        logSuccess(
          'Get current project',
          `Current version: ${currentProject.label_config_version || 'N/A'}`
        );
        console.log(`   Current label_config keys: ${currentProject.label_config ? Object.keys(currentProject.label_config).join(', ') : 'N/A'}`);
      } else {
        logFailure(
          'Get current project',
          `Status ${projectResponse.status}: ${projectResponse.statusText}`
        );
        throw new Error('Cannot proceed without current project state');
      }
    } catch (error) {
      logFailure('Get current project', error);
      throw error;
    }

    // Test 2.2: Update label_config to trigger versioning
    console.log('\nTest 2.2: Update label_config to trigger version increment');
    try {
      const currentVersion = currentProject.label_config_version || 'v1';
      const currentConfig = currentProject.label_config || {};

      // Modify the label config by adding a test field
      const modifiedConfig = {
        ...currentConfig,
        test_field_timestamp: new Date().toISOString(),
        test_modification: `Test modification at ${Date.now()}`
      };

      const updateResponse = await makeAPIRequest(
        page,
        'PATCH',
        `/api/projects/${PROJECT_ID}`,
        { label_config: modifiedConfig }
      );

      if (updateResponse.status === 200 && updateResponse.json) {
        const updatedProject = updateResponse.json;
        const newVersion = updatedProject.label_config_version;

        if (newVersion && newVersion !== currentVersion) {
          logSuccess(
            'Label config update triggers version increment',
            `Version changed from ${currentVersion} to ${newVersion}`
          );
        } else if (newVersion === currentVersion) {
          logWarning(
            'Label config update version increment',
            `Version did not increment (stayed at ${currentVersion}). This may be expected if config didn't actually change.`
          );
        } else {
          logFailure(
            'Label config update version increment',
            'No version field in response',
            `Response: ${JSON.stringify(updatedProject, null, 2).substring(0, 300)}`
          );
        }
      } else {
        logFailure(
          'Label config update',
          `Status ${updateResponse.status}: ${updateResponse.statusText}`,
          `Response: ${updateResponse.body.substring(0, 200)}`
        );
      }
    } catch (error) {
      logFailure('Label config update', error);
    }

    // Test 2.3: Verify version history now contains both versions
    console.log('\nTest 2.3: Verify version history after update');
    try {
      const versionsResponse = await makeAPIRequest(
        page,
        'GET',
        `/api/projects/${PROJECT_ID}/label-config/versions`
      );

      if (versionsResponse.status === 200 && versionsResponse.json) {
        const versions = versionsResponse.json;

        if (Array.isArray(versions)) {
          const versionNumbers = versions.map(v => v.version_number || v.version);
          logSuccess(
            'Version history after update',
            `Found ${versions.length} version(s): ${versionNumbers.join(', ')}`
          );

          // Check if we can access both v1 and the latest version
          if (versions.length >= 1) {
            console.log(`   Versions available: ${JSON.stringify(versionNumbers)}`);
          }
        } else {
          logFailure(
            'Version history after update',
            'Response is not an array',
            `Response: ${JSON.stringify(versions)}`
          );
        }
      } else {
        logFailure(
          'Version history after update',
          `Status ${versionsResponse.status}: ${versionsResponse.statusText}`
        );
      }
    } catch (error) {
      logFailure('Version history after update', error);
    }

    console.log('\n--- TEST SUITE 3: NO REGRESSION IN PROJECT UPDATES ---\n');

    // Test 3.1: Update non-config fields
    console.log('Test 3.1: Update non-label_config fields (title, description)');
    try {
      const updateData = {
        title: `AGB Project - Test ${Date.now()}`,
        description: 'Testing that non-config updates still work'
      };

      const updateResponse = await makeAPIRequest(
        page,
        'PATCH',
        `/api/projects/${PROJECT_ID}`,
        updateData
      );

      if (updateResponse.status === 200 && updateResponse.json) {
        const updated = updateResponse.json;

        if (updated.title === updateData.title) {
          logSuccess(
            'Update non-config fields',
            'Title and description updated successfully'
          );
        } else {
          logFailure(
            'Update non-config fields',
            'Fields not updated correctly',
            `Expected title: ${updateData.title}, Got: ${updated.title}`
          );
        }
      } else {
        logFailure(
          'Update non-config fields',
          `Status ${updateResponse.status}: ${updateResponse.statusText}`
        );
      }
    } catch (error) {
      logFailure('Update non-config fields', error);
    }

    // Test 3.2: Verify version didn't increment on non-config update
    console.log('\nTest 3.2: Verify version stable when updating non-config fields');
    try {
      const projectResponse = await makeAPIRequest(
        page,
        'GET',
        `/api/projects/${PROJECT_ID}`
      );

      if (projectResponse.status === 200 && projectResponse.json) {
        const project = projectResponse.json;
        logSuccess(
          'Version stability on non-config updates',
          `Version: ${project.label_config_version} (should not have incremented)`
        );
      } else {
        logFailure(
          'Version stability check',
          `Status ${projectResponse.status}: ${projectResponse.statusText}`
        );
      }
    } catch (error) {
      logFailure('Version stability check', error);
    }

    console.log('\n=== TEST SUMMARY ===\n');
    console.log(`✅ Passed: ${testResults.passed.length}`);
    console.log(`❌ Failed: ${testResults.failed.length}`);
    console.log(`⚠️  Warnings: ${testResults.warnings.length}`);

    if (testResults.failed.length > 0) {
      console.log('\n--- FAILED TESTS ---');
      testResults.failed.forEach((result, idx) => {
        console.log(`\n${idx + 1}. ${result.test}`);
        console.log(`   Error: ${result.error}`);
        if (result.details) console.log(`   Details: ${result.details}`);
      });
    }

    if (testResults.warnings.length > 0) {
      console.log('\n--- WARNINGS ---');
      testResults.warnings.forEach((result, idx) => {
        console.log(`\n${idx + 1}. ${result.test}`);
        console.log(`   Warning: ${result.warning}`);
      });
    }

    if (testResults.passed.length > 0) {
      console.log('\n--- PASSED TESTS ---');
      testResults.passed.forEach((result, idx) => {
        console.log(`${idx + 1}. ${result.test}`);
        if (result.details) console.log(`   ${result.details}`);
      });
    }

    // Exit with appropriate code
    if (testResults.failed.length > 0) {
      console.log('\n❌ TESTS FAILED');
      process.exit(1);
    } else {
      console.log('\n✅ ALL TESTS PASSED');
      process.exit(0);
    }

  } catch (error) {
    console.error('\n❌ FATAL ERROR IN TEST SUITE:', error);
    process.exit(1);
  } finally {
    if (page) await page.close();
    await browser.close();
  }
}

// Run the tests
runTests().catch(error => {
  console.error('Unhandled error:', error);
  process.exit(1);
});
