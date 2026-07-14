/**
 * Custom models API client (BYOM - bring your own model)
 *
 * Type-safe API calls for user-registered OpenAI-compatible models:
 * CRUD, project-style visibility (private / org-shared / public),
 * per-user credentials, and connection tests.
 */

import apiClient from '@/lib/api'
import type {
  CustomModel,
  CustomModelCreate,
  CustomModelTestResult,
  CustomModelUpdate,
  CustomModelVisibilityPayload,
} from './types'

export const customModelsAPI = {
  /**
   * List all custom models visible to the caller
   * (own + org-shared + public).
   */
  list: async (): Promise<CustomModel[]> => {
    const response = await apiClient.get('/custom-models')
    return response
  },

  /**
   * Get a specific custom model.
   */
  get: async (modelId: string): Promise<CustomModel> => {
    const response = await apiClient.get(`/custom-models/${modelId}`)
    return response
  },

  /**
   * Register a new custom model.
   */
  create: async (data: CustomModelCreate): Promise<CustomModel> => {
    const response = await apiClient.post('/custom-models', data)
    return response
  },

  /**
   * Update a custom model (owner or superadmin only).
   */
  update: async (
    modelId: string,
    data: CustomModelUpdate
  ): Promise<CustomModel> => {
    const response = await apiClient.patch(`/custom-models/${modelId}`, data)
    return response
  },

  /**
   * Delete a custom model (owner or superadmin only).
   *
   * Returns whether the backend hard-deleted the row or soft-deleted it
   * (deactivated + privatized) because existing generations still
   * reference the model id.
   */
  remove: async (modelId: string): Promise<{ deleted: 'soft' | 'hard' }> => {
    const response = await apiClient.delete(`/custom-models/${modelId}`)
    return response
  },

  /**
   * Change model visibility (private / org-shared / public).
   *
   * Payload shapes accepted by the backend:
   * - { is_private: true }
   * - { is_private: false, organization_ids: string[] }
   * - { is_public: true }
   */
  updateVisibility: async (
    modelId: string,
    payload: CustomModelVisibilityPayload
  ): Promise<CustomModel> => {
    const response = await apiClient.patch(
      `/custom-models/${modelId}/visibility`,
      payload
    )
    return response
  },

  /**
   * Store the calling user's own API key for this model.
   */
  setCredential: async (
    modelId: string,
    apiKey: string
  ): Promise<{ has_credential: boolean; updated_at?: string }> => {
    const response = await apiClient.put(
      `/custom-models/${modelId}/credential`,
      { api_key: apiKey }
    )
    return response
  },

  /**
   * Delete the calling user's stored API key for this model.
   */
  deleteCredential: async (modelId: string): Promise<void> => {
    await apiClient.delete(`/custom-models/${modelId}/credential`)
  },

  /**
   * Check whether the calling user has a stored key for this model.
   */
  getCredentialStatus: async (
    modelId: string
  ): Promise<{ has_credential: boolean; updated_at?: string }> => {
    const response = await apiClient.get(
      `/custom-models/${modelId}/credential`
    )
    return response
  },

  /**
   * Test the connection of a registered model. Without `api_key` the user's
   * stored credential is used; `chat_ping` additionally sends a tiny chat
   * request instead of only listing models.
   */
  testConnection: async (
    modelId: string,
    opts?: { api_key?: string; chat_ping?: boolean }
  ): Promise<CustomModelTestResult> => {
    const response = await apiClient.post(
      `/custom-models/${modelId}/test`,
      opts ?? {}
    )
    return response
  },

  /**
   * Test an endpoint before the model exists (used by the register form).
   */
  testEndpoint: async (data: {
    base_url: string
    api_key?: string
  }): Promise<CustomModelTestResult> => {
    const response = await apiClient.post('/custom-models/test', data)
    return response
  },
}
