/**
 * Tests for Tasks API client
 */

import { TasksClient } from '../tasks'

// Create a mock base API client
const mockGet = jest.fn()
const mockPost = jest.fn()
const mockDelete = jest.fn()

// We need to mock the BaseApiClient since TasksClient extends it
jest.mock('../base', () => ({
  BaseApiClient: class {
    get = mockGet
    post = mockPost
    delete = mockDelete
  },
}))

describe('TasksClient', () => {
  let client: TasksClient

  beforeEach(() => {
    jest.clearAllMocks()
    client = new TasksClient()
  })

  describe('getColumnPreferences', () => {
    it('should fetch column preferences for a project', async () => {
      const mockPrefs = {
        column_settings: {
          visibility: { col1: true, col2: false },
          order: ['col1', 'col2'],
        },
      }
      mockGet.mockResolvedValue(mockPrefs)

      const result = await client.getColumnPreferences('p1')

      expect(mockGet).toHaveBeenCalledWith('/projects/p1/column-preferences')
      expect(result).toEqual(mockPrefs)
    })

    it('should return null when preferences do not exist', async () => {
      mockGet.mockRejectedValue(new Error('Not found'))

      const result = await client.getColumnPreferences('p1')

      expect(result).toBeNull()
    })
  })

  describe('saveColumnPreferences', () => {
    it('should save column preferences', async () => {
      const preferences = {
        visibility: { col1: true },
        order: ['col1', 'col2'],
        pinning: { left: ['col1'], right: [] },
      }
      mockPost.mockResolvedValue(undefined)

      await client.saveColumnPreferences('p1', preferences)

      expect(mockPost).toHaveBeenCalledWith('/projects/p1/column-preferences', {
        column_settings: preferences,
      })
    })
  })

  describe('deleteColumnPreferences', () => {
    it('should delete column preferences', async () => {
      mockDelete.mockResolvedValue(undefined)

      await client.deleteColumnPreferences('p1')

      expect(mockDelete).toHaveBeenCalledWith(
        '/projects/p1/column-preferences'
      )
    })
  })
})
