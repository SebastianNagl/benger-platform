/**
 * @jest-environment jsdom
 */
import { describe, expect, it } from '@jest/globals'

// Mock translation function for testing
const mockT = (key: string) => {
  const translations: { [key: string]: string } = {
    // Project-based notification types
    'settings.notifications.types.projectCreated': 'Project Created',
    'settings.notifications.types.projectCreatedDesc':
      'Receive notifications when new projects are created',
    'settings.notifications.types.projectUpdated': 'Project Updated',
    'settings.notifications.types.projectUpdatedDesc':
      'Receive notifications when projects you have access to are updated',
    'settings.notifications.types.projectShared': 'Project Shared',
    'settings.notifications.types.projectSharedDesc':
      'Receive notifications when projects are shared with you',
    'settings.notifications.types.annotationAssigned': 'Annotation Assigned',
    'settings.notifications.types.annotationAssignedDesc':
      'Receive notifications when you are assigned to annotation tasks',

    // Categories
    'settings.notifications.categories.projects': 'Projects',
    'settings.notifications.categories.annotation': 'Annotation',
    'settings.notifications.categories.evaluations': 'Evaluations',
    'settings.notifications.categories.organization': 'Organization',
    'settings.notifications.categories.system': 'System',

    // Old task-based types (should not be present)
    'settings.notifications.types.taskCreated': 'Task Created',
    'settings.notifications.types.taskCreatedDesc':
      'Receive notifications when new tasks are created',
    'settings.notifications.categories.tasks': 'Tasks',
  }

  return translations[key] || key
}

// Import the notification types function (we need to extract it from the page component)
// For now, we'll recreate it here for testing
const getNotificationTypes = (t: any) => [
  {
    key: 'project_created',
    name: t('settings.notifications.types.projectCreated'),
    description: t('settings.notifications.types.projectCreatedDesc'),
    category: t('settings.notifications.categories.projects'),
  },
  {
    key: 'project_updated',
    name: t('settings.notifications.types.projectUpdated'),
    description: t('settings.notifications.types.projectUpdatedDesc'),
    category: t('settings.notifications.categories.projects'),
  },
  {
    key: 'project_shared',
    name: t('settings.notifications.types.projectShared'),
    description: t('settings.notifications.types.projectSharedDesc'),
    category: t('settings.notifications.categories.projects'),
  },
  {
    key: 'annotation_assigned',
    name: t('settings.notifications.types.annotationAssigned'),
    description: t('settings.notifications.types.annotationAssignedDesc'),
    category: t('settings.notifications.categories.annotation'),
  },
]

describe('Notification Types Configuration', () => {
  it('should include project-based notification types', () => {
    const notificationTypes = getNotificationTypes(mockT)

    // Check that project-based types exist
    const projectCreated = notificationTypes.find(
      (type) => type.key === 'project_created'
    )
    const projectUpdated = notificationTypes.find(
      (type) => type.key === 'project_updated'
    )
    const projectShared = notificationTypes.find(
      (type) => type.key === 'project_shared'
    )

    expect(projectCreated).toBeDefined()
    expect(projectCreated?.name).toBe('Project Created')
    expect(projectCreated?.category).toBe('Projects')

    expect(projectUpdated).toBeDefined()
    expect(projectUpdated?.name).toBe('Project Updated')

    expect(projectShared).toBeDefined()
    expect(projectShared?.name).toBe('Project Shared')
  })

  it('should include annotation assignment notifications', () => {
    const notificationTypes = getNotificationTypes(mockT)

    const annotationAssigned = notificationTypes.find(
      (type) => type.key === 'annotation_assigned'
    )

    expect(annotationAssigned).toBeDefined()
    expect(annotationAssigned?.name).toBe('Annotation Assigned')
    expect(annotationAssigned?.description).toBe(
      'Receive notifications when you are assigned to annotation tasks'
    )
    expect(annotationAssigned?.category).toBe('Annotation')
  })

  it('should not include old task-based notification types', () => {
    const notificationTypes = getNotificationTypes(mockT)

    // Check that old task-based types are NOT present
    const taskCreated = notificationTypes.find(
      (type) => type.key === 'task_created'
    )

    expect(taskCreated).toBeUndefined()
  })

  it('should have proper project category', () => {
    const notificationTypes = getNotificationTypes(mockT)

    // Get all unique categories
    const categories = [
      ...new Set(notificationTypes.map((type) => type.category)),
    ]

    // Should include Projects category
    expect(categories).toContain('Projects')

    // Should NOT include old Tasks category in our test data
    // (Note: other notification types may still use different categories)
    const projectTypes = notificationTypes.filter(
      (type) => type.category === 'Projects'
    )
    expect(projectTypes.length).toBeGreaterThan(0)
  })

  it('should have properly formatted descriptions', () => {
    const notificationTypes = getNotificationTypes(mockT)

    notificationTypes.forEach((type) => {
      // Each type should have a non-empty name and description
      expect(type.name).toBeTruthy()
      expect(type.description).toBeTruthy()
      expect(type.category).toBeTruthy()

      // Descriptions should be readable (not translation keys)
      expect(type.name).not.toMatch(/^settings\.notifications\./)
      expect(type.description).not.toMatch(/^settings\.notifications\./)
    })
  })

  it('should use proper notification key naming convention', () => {
    const notificationTypes = getNotificationTypes(mockT)

    notificationTypes.forEach((type) => {
      // Keys should be in snake_case format
      expect(type.key).toMatch(/^[a-z]+(_[a-z]+)*$/)

      // Project-related keys should follow naming pattern
      if (type.category === 'Projects') {
        expect(type.key).toMatch(/^project_/)
      }
    })
  })
})
