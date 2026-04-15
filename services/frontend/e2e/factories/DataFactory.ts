/**
 * TestDataFactory - Realistic Test Data Generation
 *
 * Generates realistic test data for E2E testing including projects,
 * tasks, annotations, and user data
 *
 * Part of Issue #471 Implementation
 */

import { faker } from '@faker-js/faker'
import { Page } from '@playwright/test'

export interface ProjectData {
  name: string
  description: string
  template: string
  visibility: 'public' | 'private'
  organizations: string[]
  settings?: Record<string, any>
}

export interface TaskData {
  project_id: string
  data: {
    text?: string
    document_id?: string
    page_number?: number
    [key: string]: any
  }
  metadata?: Record<string, any>
}

export interface AnnotationData {
  task_id: string
  result: any[]
  was_cancelled?: boolean
  ground_truth?: boolean
  lead_time?: number
}

export class TestDataFactory {
  /**
   * Create realistic project data
   */
  static createProject(overrides: Partial<ProjectData> = {}): ProjectData {
    const templates = [
      'legal-document-review',
      'question-answering',
      'named-entity-recognition',
      'text-classification',
      'sentiment-analysis',
    ]

    return {
      name: faker.company.name() + ' ' + faker.word.adjective() + ' Analysis',
      description: faker.lorem.paragraph(3),
      template: faker.helpers.arrayElement(templates),
      visibility: faker.helpers.arrayElement(['public', 'private']),
      organizations: ['test-org-1'],
      settings: {
        enable_expert_mode: faker.datatype.boolean(),
        show_annotation_history: true,
        show_predictions: faker.datatype.boolean(),
        maximum_annotations: faker.number.int({ min: 1, max: 5 }),
      },
      ...overrides,
    }
  }

  /**
   * Create bulk tasks for a project
   */
  static createBulkTasks(count: number, projectId: string): TaskData[] {
    return Array.from({ length: count }, (_, i) => ({
      project_id: projectId,
      data: {
        text: faker.lorem.paragraphs(faker.number.int({ min: 1, max: 5 })),
        document_id: faker.string.uuid(),
        page_number: i + 1,
        source: faker.helpers.arrayElement([
          'court_decision',
          'contract',
          'legislation',
          'brief',
        ]),
        category: faker.helpers.arrayElement([
          'civil',
          'criminal',
          'constitutional',
          'administrative',
        ]),
        date: faker.date.past().toISOString(),
        difficulty: faker.helpers.arrayElement(['easy', 'medium', 'hard']),
      },
      metadata: {
        source: 'test-import',
        created_at: new Date().toISOString(),
        import_batch: faker.string.uuid(),
        priority: faker.number.int({ min: 1, max: 10 }),
      },
    }))
  }

  /**
   * Generate CSV content for import
   */
  static generateCSV(
    rowCount: number,
    includeAnnotations: boolean = false
  ): string {
    const headers = ['text', 'document_id', 'category', 'priority']
    if (includeAnnotations) {
      headers.push('annotation', 'annotation_confidence')
    }

    const rows = [headers.join(',')]

    for (let i = 0; i < rowCount; i++) {
      const row = [
        `"${faker.lorem.sentence().replace(/"/g, '""')}"`, // Escape quotes in CSV
        faker.string.uuid(),
        faker.helpers.arrayElement(['civil', 'criminal', 'constitutional']),
        faker.number.int({ min: 1, max: 10 }),
      ]

      if (includeAnnotations) {
        row.push(
          `"${faker.lorem.words(3).replace(/"/g, '""')}"`,
          faker.number.float({ min: 0.5, max: 1, precision: 0.01 }).toString()
        )
      }

      rows.push(row.join(','))
    }

    return rows.join('\n')
  }

  /**
   * Generate JSON content for import
   */
  static generateJSON(
    taskCount: number,
    includeAnnotations: boolean = false
  ): string {
    const tasks = []

    for (let i = 0; i < taskCount; i++) {
      const task: any = {
        data: {
          text: faker.lorem.paragraph(),
          document_id: faker.string.uuid(),
          category: faker.helpers.arrayElement([
            'civil',
            'criminal',
            'constitutional',
          ]),
          metadata: {
            priority: faker.number.int({ min: 1, max: 10 }),
            source: 'test-import',
            created_at: new Date().toISOString(),
          },
        },
      }

      if (includeAnnotations) {
        task.annotations = [
          {
            result: [
              {
                value: {
                  text: faker.lorem.sentence(),
                  confidence: faker.number.float({
                    min: 0.5,
                    max: 1,
                    precision: 0.01,
                  }),
                },
                from_name: 'answer',
                to_name: 'text',
                type: 'textarea',
              },
            ],
            was_cancelled: false,
            ground_truth: faker.datatype.boolean(),
            created_at: faker.date.recent().toISOString(),
            updated_at: faker.date.recent().toISOString(),
            lead_time: faker.number.int({ min: 10, max: 300 }),
          },
        ]
      }

      tasks.push(task)
    }

    return JSON.stringify(tasks, null, 2)
  }

  /**
   * Generate XML content for import (Label Studio format)
   */
  static generateXML(taskCount: number): string {
    let xml = '<?xml version="1.0" encoding="UTF-8"?>\n<tasks>\n'

    for (let i = 0; i < taskCount; i++) {
      xml += '  <task>\n'
      xml += `    <text>${this.escapeXML(faker.lorem.paragraph())}</text>\n`
      xml += `    <document_id>${faker.string.uuid()}</document_id>\n`
      xml += `    <category>${faker.helpers.arrayElement(['civil', 'criminal', 'constitutional'])}</category>\n`
      xml += `    <priority>${faker.number.int({ min: 1, max: 10 })}</priority>\n`
      xml += '  </task>\n'
    }

    xml += '</tasks>'
    return xml
  }

  /**
   * Escape XML special characters
   */
  private static escapeXML(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;')
  }

  /**
   * Import CSV file to a project
   */
  static async importCSV(
    page: Page,
    csvContent: string,
    fileName: string = 'test-data.csv'
  ): Promise<void> {
    const buffer = Buffer.from(csvContent)

    // Set up file input
    await page.setInputFiles(
      '[data-testid="file-upload"], input[type="file"]',
      {
        name: fileName,
        mimeType: 'text/csv',
        buffer: buffer,
      }
    )

    // Click import button
    const importButton = page.locator(
      '[data-testid="import-button"], button:has-text("Import")'
    )
    await importButton.click()

    // Wait for import success
    await page.waitForSelector(
      '[data-testid="import-success"], text=/imported successfully/i',
      {
        timeout: 30000,
      }
    )
  }

  /**
   * Import JSON file to a project
   */
  static async importJSON(
    page: Page,
    jsonContent: string,
    fileName: string = 'test-data.json'
  ): Promise<void> {
    const buffer = Buffer.from(jsonContent)

    await page.setInputFiles(
      '[data-testid="file-upload"], input[type="file"]',
      {
        name: fileName,
        mimeType: 'application/json',
        buffer: buffer,
      }
    )

    const importButton = page.locator(
      '[data-testid="import-button"], button:has-text("Import")'
    )
    await importButton.click()

    await page.waitForSelector(
      '[data-testid="import-success"], text=/imported successfully/i',
      {
        timeout: 30000,
      }
    )
  }

  /**
   * Create realistic annotation data
   */
  static createAnnotation(
    taskId: string,
    annotationType: string = 'text'
  ): AnnotationData {
    const annotationTypes: Record<string, any> = {
      text: {
        value: {
          text: faker.lorem.sentence(),
        },
        from_name: 'answer',
        to_name: 'text',
        type: 'textarea',
      },
      choices: {
        value: {
          choices: [
            faker.helpers.arrayElement(['Option A', 'Option B', 'Option C']),
          ],
        },
        from_name: 'classification',
        to_name: 'text',
        type: 'choices',
      },
      labels: {
        value: {
          start: faker.number.int({ min: 0, max: 100 }),
          end: faker.number.int({ min: 101, max: 200 }),
          text: faker.lorem.words(5),
          labels: [
            faker.helpers.arrayElement([
              'PERSON',
              'ORGANIZATION',
              'LOCATION',
              'DATE',
            ]),
          ],
        },
        from_name: 'label',
        to_name: 'text',
        type: 'labels',
      },
      rating: {
        value: {
          rating: faker.number.int({ min: 1, max: 5 }),
        },
        from_name: 'rating',
        to_name: 'text',
        type: 'rating',
      },
    }

    return {
      task_id: taskId,
      result: [annotationTypes[annotationType] || annotationTypes.text],
      was_cancelled: false,
      ground_truth: faker.datatype.boolean(),
      lead_time: faker.number.int({ min: 10, max: 600 }),
    }
  }

  /**
   * Create user data for testing
   */
  static createUser(overrides: Partial<any> = {}): any {
    const firstName = faker.person.firstName()
    const lastName = faker.person.lastName()
    const email = faker.internet.email({ firstName, lastName }).toLowerCase()

    return {
      email,
      username: email.split('@')[0],
      first_name: firstName,
      last_name: lastName,
      role: faker.helpers.arrayElement([
        'user',
        'annotator',
        'contributor',
        'org_admin',
        'superadmin',
      ]),
      organization: faker.company.name(),
      is_active: true,
      created_at: faker.date.past().toISOString(),
      ...overrides,
    }
  }

  /**
   * Create organization data
   */
  static createOrganization(overrides: Partial<any> = {}): any {
    return {
      name: faker.company.name(),
      description: faker.company.catchPhrase(),
      website: faker.internet.url(),
      contact_email: faker.internet.email(),
      max_users: faker.number.int({ min: 10, max: 1000 }),
      max_projects: faker.number.int({ min: 5, max: 100 }),
      created_at: faker.date.past().toISOString(),
      settings: {
        allow_public_projects: faker.datatype.boolean(),
        require_2fa: faker.datatype.boolean(),
        data_retention_days: faker.number.int({ min: 30, max: 365 }),
      },
      ...overrides,
    }
  }

  /**
   * Generate realistic legal document text
   */
  static generateLegalText(
    type: 'contract' | 'court_decision' | 'legislation' | 'brief' = 'contract'
  ): string {
    const templates = {
      contract: [
        'This Agreement is entered into as of',
        'WHEREAS, the parties wish to',
        'NOW, THEREFORE, in consideration of',
        'The parties hereby agree as follows',
        'This Agreement shall be governed by',
      ],
      court_decision: [
        'Before the Court is',
        'The Court finds that',
        'Based on the foregoing',
        'It is hereby ORDERED that',
        'This decision may be appealed',
      ],
      legislation: [
        'Be it enacted by',
        'Section 1. Short Title',
        'Section 2. Definitions',
        'Section 3. General Provisions',
        'Section 4. Effective Date',
      ],
      brief: [
        'Comes now the Plaintiff',
        'Statement of Facts',
        'Legal Argument',
        'Conclusion and Prayer for Relief',
        'Respectfully submitted',
      ],
    }

    const selectedTemplates = templates[type]
    const paragraphs = []

    for (const template of selectedTemplates) {
      paragraphs.push(`${template} ${faker.lorem.paragraph()}`)
    }

    return paragraphs.join('\n\n')
  }

  /**
   * Create template configuration
   */
  static createTemplate(type: string = 'question-answering'): any {
    const templates: Record<string, any> = {
      'question-answering': {
        name: 'Question Answering Template',
        config: `
          <View>
            <Text name="text" value="$text"/>
            <TextArea name="answer" toName="text" placeholder="Enter your answer here"/>
          </View>
        `,
        description: 'Template for question answering tasks',
      },
      'named-entity-recognition': {
        name: 'NER Template',
        config: `
          <View>
            <Text name="text" value="$text"/>
            <Labels name="label" toName="text">
              <Label value="PERSON" background="red"/>
              <Label value="ORGANIZATION" background="blue"/>
              <Label value="LOCATION" background="green"/>
              <Label value="DATE" background="yellow"/>
            </Labels>
          </View>
        `,
        description: 'Template for named entity recognition',
      },
      'text-classification': {
        name: 'Text Classification Template',
        config: `
          <View>
            <Text name="text" value="$text"/>
            <Choices name="classification" toName="text">
              <Choice value="Positive"/>
              <Choice value="Neutral"/>
              <Choice value="Negative"/>
            </Choices>
          </View>
        `,
        description: 'Template for text classification',
      },
    }

    return templates[type] || templates['question-answering']
  }
}
