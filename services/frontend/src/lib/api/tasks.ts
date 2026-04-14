/**
 * Tasks API client
 *
 * Provides task-related API methods including column preferences
 * Note: In BenGER, "Tasks" are actually projects (containers for data)
 */

import { BaseApiClient } from './base'

export class TasksClient extends BaseApiClient {
  /**
   * Get column preferences for a task/project
   */
  async getColumnPreferences(taskId: string): Promise<{
    column_settings?: {
      visibility?: Record<string, boolean>
      order?: string[]
      pinning?: { left?: string[]; right?: string[] }
    }
  } | null> {
    try {
      return await this.get(`/projects/${taskId}/column-preferences`)
    } catch (error) {
      // Return null if preferences don't exist
      return null
    }
  }

  /**
   * Save column preferences for a task/project
   */
  async saveColumnPreferences(
    taskId: string,
    preferences: {
      visibility?: Record<string, boolean>
      order?: string[]
      pinning?: { left?: string[]; right?: string[] }
    }
  ): Promise<void> {
    await this.post(`/projects/${taskId}/column-preferences`, {
      column_settings: preferences,
    })
  }

  /**
   * Delete column preferences for a task/project
   */
  async deleteColumnPreferences(taskId: string): Promise<void> {
    await this.delete(`/projects/${taskId}/column-preferences`)
  }
}
