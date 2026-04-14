/**
 * Authentication API client
 * Handles login, signup, and user authentication using HttpOnly cookies
 */

import { BaseApiClient } from './base'
import {
  AuthResponse,
  MandatoryProfileStatus,
  Organization,
  ProfileConfirmationResponse,
  ProfileHistoryEntry,
  User,
} from './types'

export class AuthClient extends BaseApiClient {
  /**
   * Login user with username and password
   * The JWT will be set as an HttpOnly cookie by the backend
   * SECURITY: No localStorage storage - cookies only for XSS protection
   */
  async login(username: string, password: string): Promise<AuthResponse> {
    const response = await this.request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })

    return response
  }

  /**
   * Register new user with legal expertise data and mandatory profile fields
   */
  async signup(
    username: string,
    email: string,
    name: string,
    password: string,
    profileData?: {
      // Legal expertise
      legal_expertise_level?: string
      german_proficiency?: string
      degree_program_type?: string
      current_semester?: number
      legal_specializations?: string[]
      // Demographics (Issue #1206)
      gender?: string
      age?: number
      job?: string
      years_of_experience?: number
      // Subjective competence (Issue #1206)
      subjective_competence_civil?: number
      subjective_competence_public?: number
      subjective_competence_criminal?: number
      // Grades (Issue #1206)
      grade_zwischenpruefung?: number
      grade_vorgeruecktenubung?: number
      grade_first_staatsexamen?: number
      grade_second_staatsexamen?: number
      // Psychometric scales (Issue #1206)
      ati_s_scores?: Record<string, number>
      ptt_a_scores?: Record<string, number>
      ki_experience_scores?: Record<string, number>
    },
    invitationToken?: string
  ): Promise<User> {
    const signupData: Record<string, unknown> = {
      username,
      email,
      name,
      password,
    }

    // Add profile fields if provided
    if (profileData) {
      Object.entries(profileData).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          signupData[key] = value
        }
      })
    }

    // Add invitation token if provided
    if (invitationToken) {
      signupData.invitation_token = invitationToken
    }

    return this.request('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(signupData),
    })
  }

  /**
   * Get current user information
   * Uses the JWT from HttpOnly cookie automatically
   */
  async getUser(): Promise<User> {
    return this.authCheckRequest('/auth/me')
  }

  /**
   * Get user info and organization contexts in a single call.
   * Reduces page load from 2 API calls to 1.
   */
  async getUserContexts(): Promise<{
    user: User
    organizations: Organization[]
    private_mode_available: boolean
  }> {
    return this.authCheckRequest('/auth/me/contexts')
  }

  /**
   * Alias for getUser for backward compatibility
   */
  async getCurrentUser(): Promise<User> {
    return this.getUser()
  }

  /**
   * Verify if the current token is valid
   */
  async verifyToken(): Promise<{ valid: boolean }> {
    return this.request('/auth/verify')
  }

  /**
   * Logout user
   * The backend will clear the HttpOnly cookie automatically
   * SECURITY: No localStorage cleanup needed - cookies only
   */
  async logout(): Promise<void> {
    // SECURITY FIX: Removed localStorage access
    // Authentication cookies are automatically cleared by the backend
    // This ensures no client-side token storage exists

    // The base client now handles 401 responses for logout as expected behavior
    return this.request('/auth/logout', {
      method: 'POST',
    })
  }

  /**
   * Get current user's profile information
   */
  async getProfile(): Promise<User> {
    // CRITICAL: Always clear cache before fetching profile to prevent pollution
    this.clearCache()

    // Add timestamp to prevent any browser-level caching
    const timestamp = Date.now()
    const endpoint = `/auth/profile?_t=${timestamp}`

    // Use authCheckRequest to bypass our caching for profile data
    // This ensures we always get fresh user data
    return this.authCheckRequest(endpoint)
  }

  /**
   * Update current user's profile information
   */
  async updateProfile(profileData: {
    name?: string
    email?: string
    use_pseudonym?: boolean
    timezone?: string
    enable_quiet_hours?: boolean
    quiet_hours_start?: string
    quiet_hours_end?: string
    enable_email_digest?: boolean
    digest_frequency?: string
    digest_time?: string
    digest_days?: string
    // Demographic fields
    age?: number
    job?: string
    years_of_experience?: number
    // Legal expertise fields
    legal_expertise_level?: string
    german_proficiency?: string
    degree_program_type?: string
    current_semester?: number
    legal_specializations?: string[]
    // German state exam fields
    german_state_exams_count?: number
    german_state_exams_data?: Array<{
      location: string
      date: string
      grade: string
    }>
    // Gender (Issue #1206)
    gender?: string
    // Subjective competence (Issue #1206)
    subjective_competence_civil?: number
    subjective_competence_public?: number
    subjective_competence_criminal?: number
    // Grades (Issue #1206)
    grade_zwischenpruefung?: number
    grade_vorgeruecktenubung?: number
    grade_first_staatsexamen?: number
    grade_second_staatsexamen?: number
    // Psychometric scales (Issue #1206)
    ati_s_scores?: Record<string, number>
    ptt_a_scores?: Record<string, number>
    ki_experience_scores?: Record<string, number>
  }): Promise<User> {
    const result = await this.request('/auth/profile', {
      method: 'PUT',
      body: JSON.stringify(profileData),
    })
    // Saving profile also confirms it (Issue #1206), so invalidate the status cache
    this.invalidateCache('/auth/mandatory-profile-status')
    return result
  }

  /**
   * Get mandatory profile completion status (Issue #1206)
   */
  async getMandatoryProfileStatus(): Promise<MandatoryProfileStatus> {
    return this.request('/auth/mandatory-profile-status')
  }

  /**
   * Confirm/re-confirm profile data (Issue #1206)
   */
  async confirmProfile(): Promise<ProfileConfirmationResponse> {
    const result = await this.request('/auth/confirm-profile', {
      method: 'POST',
    })
    // Invalidate cached status so the next check returns fresh data
    this.invalidateCache('/auth/mandatory-profile-status')
    return result
  }

  /**
   * Get profile change history (superadmin only) (Issue #1206)
   */
  async getProfileHistory(): Promise<ProfileHistoryEntry[]> {
    return this.request('/auth/profile-history')
  }

  /**
   * Change current user's password
   */
  async changePassword(passwordData: {
    current_password: string
    new_password: string
    confirm_password: string
  }): Promise<{ message: string }> {
    return this.request('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify(passwordData),
    })
  }
}
