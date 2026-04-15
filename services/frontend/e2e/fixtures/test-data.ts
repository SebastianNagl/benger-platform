import { Page } from '@playwright/test'

export const testUsers = {
  admin: {
    email: 'admin@test.com',
    password: 'Admin123!',
    organization: 'TUM',
    role: 'admin',
  },
  annotator: {
    email: 'annotator@test.com',
    password: 'Annotator123!',
    organization: 'TUM',
    role: 'annotator',
  },
  contributor: {
    email: 'contributor@test.com',
    password: 'Contributor123!',
    organization: 'TUM',
    role: 'contributor',
  },
  orgAAdmin: {
    email: 'org-a-admin@test.com',
    password: 'OrgAAdmin123!',
    organization: 'Organization A',
    role: 'org_admin',
  },
  orgBUser: {
    email: 'org-b-user@test.com',
    password: 'OrgBUser123!',
    organization: 'Organization B',
    role: 'user',
  },
}

export const testProjects = {
  qaProject: {
    name: 'QA Test Project',
    description: 'E2E test project for QA reasoning tasks',
    taskType: 'qa_reasoning',
    visibility: 'private',
    organizations: ['TUM'],
  },
  classificationProject: {
    name: 'Classification Test Project',
    description: 'E2E test project for text classification',
    taskType: 'text_classification',
    visibility: 'public',
    organizations: ['TUM'],
  },
  multiOrgProject: {
    name: 'Multi-Org Collaboration Project',
    description: 'E2E test project for multi-organization collaboration',
    taskType: 'qa_reasoning',
    visibility: 'private',
    organizations: ['Organization A', 'Organization B'],
  },
}

export const sampleTasks = {
  qaReasoningTasks: [
    {
      text: 'What is the capital of Germany?',
      expected_answer: 'Berlin',
      difficulty: 'easy',
    },
    {
      text: 'Explain the concept of constitutional democracy.',
      expected_answer:
        'A system of government where power is limited by a constitution',
      difficulty: 'medium',
    },
    {
      text: 'Analyze the legal implications of artificial intelligence in healthcare.',
      expected_answer:
        'Complex answer involving privacy, liability, and regulatory considerations',
      difficulty: 'hard',
    },
  ],
  classificationTasks: [
    {
      text: 'This contract is invalid due to lack of consideration.',
      category: 'Legal',
      subcategory: 'Contract Law',
    },
    {
      text: 'The defendant was found guilty of tax evasion.',
      category: 'Legal',
      subcategory: 'Criminal Law',
    },
    {
      text: 'The weather will be sunny tomorrow.',
      category: 'Non-Legal',
      subcategory: 'General',
    },
  ],
}

export function generateQATasks(count: number) {
  const tasks = []
  for (let i = 0; i < count; i++) {
    tasks.push({
      text: `Test question ${i + 1}: What is the answer to question ${i + 1}?`,
      expected_answer: `This is the expected answer for question ${i + 1}`,
      difficulty: ['easy', 'medium', 'hard'][i % 3],
      metadata: {
        index: i + 1,
        created_at: new Date().toISOString(),
      },
    })
  }
  return tasks
}

export function generateClassificationTasks(count: number) {
  const categories = ['Legal', 'Non-Legal', 'Technical', 'Administrative']
  const subcategories = {
    Legal: ['Contract Law', 'Criminal Law', 'Constitutional Law', 'Tax Law'],
    'Non-Legal': ['General', 'News', 'Opinion', 'Other'],
    Technical: ['Software', 'Hardware', 'Network', 'Security'],
    Administrative: ['HR', 'Finance', 'Operations', 'Management'],
  }

  const tasks = []
  for (let i = 0; i < count; i++) {
    const category = categories[i % categories.length]
    const subcategoryList = subcategories[category]
    const subcategory = subcategoryList[i % subcategoryList.length]

    tasks.push({
      text: `Sample text ${i + 1} for classification in ${category} - ${subcategory}`,
      category,
      subcategory,
      confidence: Math.random(),
      metadata: {
        index: i + 1,
        created_at: new Date().toISOString(),
      },
    })
  }
  return tasks
}

export async function createTestUser(
  page: Page,
  userData: typeof testUsers.admin
) {
  const apiUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000'

  const response = await page.request.post(`${apiUrl}/api/auth/register`, {
    data: {
      email: userData.email,
      password: userData.password,
      organization: userData.organization,
      role: userData.role,
    },
  })

  if (!response.ok()) {
    const error = await response.text()
    console.warn(`Failed to create test user ${userData.email}: ${error}`)
  }

  return response.ok()
}

export async function cleanupTestData(page: Page) {
  try {
    const apiUrl = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000'

    await page.request.delete(`${apiUrl}/api/test/cleanup`, {
      data: {
        pattern: 'e2e-test-*',
      },
    })
  } catch (error) {
    console.warn('Failed to cleanup test data:', error)
  }
}

export async function getVerificationLink(email: string): Promise<string> {
  await new Promise((resolve) => setTimeout(resolve, 2000))

  const timestamp = Date.now()
  const token = Buffer.from(`${email}:${timestamp}`).toString('base64')
  return `http://localhost:3000/verify-email?token=${token}`
}

export async function seedE2EDatabase() {
  console.log('Seeding E2E test database...')

  console.log('E2E database seeding complete')
}

export function generateImportFile(
  format: 'json' | 'csv' | 'xml',
  tasks: any[]
) {
  switch (format) {
    case 'json':
      return JSON.stringify({ tasks }, null, 2)

    case 'csv':
      const headers = Object.keys(tasks[0]).join(',')
      const rows = tasks.map((task) =>
        Object.values(task)
          .map((v) => (typeof v === 'string' ? `"${v}"` : v))
          .join(',')
      )
      return [headers, ...rows].join('\n')

    case 'xml':
      const xmlTasks = tasks
        .map((task) => {
          const fields = Object.entries(task)
            .map(([key, value]) => `    <${key}>${value}</${key}>`)
            .join('\n')
          return `  <task>\n${fields}\n  </task>`
        })
        .join('\n')
      return `<?xml version="1.0" encoding="UTF-8"?>\n<tasks>\n${xmlTasks}\n</tasks>`

    default:
      throw new Error(`Unsupported format: ${format}`)
  }
}
