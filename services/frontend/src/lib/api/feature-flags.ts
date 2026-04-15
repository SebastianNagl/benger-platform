/**
 * Feature Flag API Client
 * Provides methods for interacting with feature flags
 */

import { BaseApiClient } from './base'
import {
  FeatureFlag,
  FeatureFlagCreate,
  FeatureFlagStatus,
  FeatureFlagUpdate,
} from './types'

export class FeatureFlagsClient extends BaseApiClient {
  /**
   * Get all feature flags for admin management (Admin only)
   */
  async getAllFeatureFlagsForAdmin(): Promise<FeatureFlag[]> {
    const response = await this.get('/feature-flags')
    return response
  }

  /**
   * Create a new feature flag (Admin only)
   */
  async createFeatureFlag(flagData: FeatureFlagCreate): Promise<FeatureFlag> {
    const response = await this.post('/feature-flags', flagData)
    return response
  }

  /**
   * Get a specific feature flag (Admin only)
   */
  async getFeatureFlag(flagId: string): Promise<FeatureFlag> {
    const response = await this.get(`/feature-flags/${flagId}`)
    return response
  }

  /**
   * Update a feature flag (Admin only)
   */
  async updateFeatureFlag(
    flagId: string,
    updates: FeatureFlagUpdate
  ): Promise<FeatureFlag> {
    const response = await this.put(`/feature-flags/${flagId}`, updates)
    return response
  }

  /**
   * Delete a feature flag (Admin only)
   */
  async deleteFeatureFlag(flagId: string): Promise<void> {
    await this.delete(`/feature-flags/${flagId}`)
  }

  /**
   * Check if a feature flag is enabled (global for all users)
   */
  async checkFeatureFlag(flagName: string): Promise<FeatureFlagStatus> {
    const response = await this.get(`/feature-flags/check/${flagName}`)
    return response
  }

  /**
   * Get all feature flags (global, same for all users)
   */
  async getFeatureFlags(): Promise<Record<string, boolean>> {
    // Add cache-busting parameter to ensure fresh data
    const searchParams = new URLSearchParams()
    searchParams.append('_t', Date.now().toString())
    const url = `/feature-flags/all?${searchParams.toString()}`
    const response = await this.get(url)
    return response
  }

  // User and organization overrides removed - feature flags are global
}
