/**
 * API client for default configuration endpoints (non-admin public endpoints)
 */

import { BaseApiClient } from './base'

// Create a dedicated instance to avoid circular dependencies
const defaultsClient = new BaseApiClient()

// Export function to configure the client with auth failure handler and organization context
export function configureAdminDefaultsClient(
  authFailureHandler?: () => void,
  organizationContextProvider?: () => string | null
) {
  if (authFailureHandler) {
    defaultsClient.setAuthFailureHandler(authFailureHandler)
  }
  if (organizationContextProvider) {
    defaultsClient.setOrganizationContextProvider(organizationContextProvider)
  }
}

export interface DefaultPrompts {
  task_type: string
  system_prompt?: string
  instruction_prompt?: string
  evaluation_prompt?: string
  updated_at?: string
  updated_by?: string
}

export interface DefaultConfig {
  task_type: string
  temperature: number
  max_tokens: number
  generation_config: Record<string, any>
}

/**
 * Get default prompts for a specific task type
 * Uses public endpoint that doesn't require superadmin privileges
 */
export async function getDefaultPrompts(
  taskType: string
): Promise<DefaultPrompts> {
  const response = await defaultsClient.get(`/api/default-prompts/${taskType}`)
  return response
}

/**
 * Get default configuration for a specific task type
 */
export async function getDefaultConfig(
  taskType: string
): Promise<DefaultConfig> {
  const response = await defaultsClient.get(`/api/defaults/config/${taskType}`)
  return response
}

/**
 * Get default configurations for all task types
 */
export async function getAllDefaultConfigs(): Promise<
  Record<string, DefaultConfig>
> {
  const response = await defaultsClient.get('/api/defaults/config')
  return response
}
