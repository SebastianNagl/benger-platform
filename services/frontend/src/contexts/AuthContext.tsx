'use client'

import { ApiClientContextProvider } from '@/contexts/ApiClientContext'
import { ApiClient, createApiClient, Organization, User } from '@/lib/api'
import { devAuthHelper } from '@/lib/auth/devAuthHelper'
import { redirectToLoginAsExpired } from '@/lib/auth/sessionExpired'
import { sessionManager } from '@/lib/auth/sessionManager'
import { logger } from '@/lib/utils/logger'
import { getPrivateUrl } from '@/lib/utils/subdomain'
import { translate } from '@/lib/utils/translate'
import { useNotificationStore } from '@/stores/notificationStore'
import { authRedirect, publicRoutes } from '@/utils/authRedirect'
import { useRouter } from 'next/navigation'
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

interface AuthContextType {
  user: User | null
  login: (username: string, password: string) => Promise<void>
  signup: (
    username: string,
    email: string,
    name: string,
    password: string,
    profileData?: {
      legal_expertise_level?: string
      german_proficiency?: string
      degree_program_type?: string
      current_semester?: number
      legal_specializations?: string[]
      gender?: string
      age?: number
      job?: string
      years_of_experience?: number
      subjective_competence_civil?: number
      subjective_competence_public?: number
      subjective_competence_criminal?: number
      grade_zwischenpruefung?: number
      grade_vorgeruecktenubung?: number
      grade_first_staatsexamen?: number
      grade_second_staatsexamen?: number
      ati_s_scores?: Record<string, number>
      ptt_a_scores?: Record<string, number>
      ki_experience_scores?: Record<string, number>
      research_data_consent_accepted?: boolean
    },
    invitationToken?: string,
  ) => Promise<void>
  logout: () => Promise<void>
  updateUser: (userData: Partial<User>) => void
  isLoading: boolean
  refreshAuth: () => Promise<void>
  apiClient: ApiClient
  /**
   * Every organization the user belongs to, with their role in each. Purely
   * informational: the API decides access per project from all memberships,
   * and a new project names its organization in the wizard, so there is no
   * "current" organization to select any more.
   */
  organizations: Organization[]
  refreshOrganizations: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const router = useRouter()

  // Prevent multiple simultaneous auth checks
  const authInitializationInProgress = useRef(false)
  const hasInitialized = useRef(false)
  const lastAuthCheckTime = useRef(0)
  const authCheckDebounceTimer = useRef<NodeJS.Timeout | null>(null)

  // One API client with a stable reference. The auth-failure handler is
  // applied via the effect below because it's a useCallback that changes
  // with deps.
  const apiClient = useMemo(() => createApiClient(), [])

  // Set up auth failure handler with stable callback
  const handleAuthFailure = useCallback(() => {
    // CRITICAL: Ignore auth failures while login is in progress to prevent immediate logout
    if (sessionManager.isLoginInProgress()) {
      logger.debug('Ignoring auth failure - login in progress')
      return
    }

    // Ignore auth failures during initialization — initializeAuth handles them
    // in its own catch block (public routes → skip, protected routes → clear state).
    if (authInitializationInProgress.current) {
      logger.debug('Ignoring auth failure - initialization in progress')
      return
    }

    // Never redirect to /login when already on a public route.
    // Race condition: during initializeAuth, getUser() rejects immediately (authCheckRequest,
    // no token refresh) while getOrganizations() is still doing async token refresh.
    // Promise.all rejects early → finally clears authInitializationInProgress → then
    // getOrganizations' refresh fails → onAuthFailure fires with the guard already cleared.
    // Public routes don't require auth, so redirecting would be wrong regardless.
    const currentPath =
      typeof window !== 'undefined' ? window.location.pathname : ''
    if (authRedirect.isPublicRoute(currentPath)) {
      logger.debug('Ignoring auth failure - on public route:', currentPath)
      setUser(null)
      setOrganizations([])
      return
    }

    // Authentication failed on a protected route — redirect to login WITH
    // the standard "session expired" toast (parity with WebSocket-close
    // 4401/4403 handling in the EvaluationResults / Generation components).
    // The helper does a full-page navigation, so the local state clear
    // below is belt-and-suspenders (the unmount handles it too).
    setUser(null)
    setOrganizations([])
    redirectToLoginAsExpired()
  }, [])

  React.useEffect(() => {
    apiClient.setAuthFailureHandler(handleAuthFailure)
  }, [apiClient, handleAuthFailure])

  // Silent token refresh function
  const silentTokenRefresh = useCallback(async () => {
    try {
      const response = await fetch('/api/auth/refresh', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        // Silent token refresh successful
        // Token cookies are automatically updated by the server
        return true
      } else {
        // Silent token refresh failed
        return false
      }
    } catch (error) {
      // Silent token refresh error
      return false
    }
  }, [])

  // Set up automatic token refresh (5 minutes before expiry)
  React.useEffect(() => {
    let refreshInterval: NodeJS.Timeout | null = null

    if (user && !isLoading) {
      // Refresh token every 25 minutes (5 minutes before 30-minute expiry)
      refreshInterval = setInterval(
        async () => {
          try {
            await silentTokenRefresh()
          } catch (error) {
            // Silent token refresh failed
          }
        },
        25 * 60 * 1000,
      ) // 25 minutes
    }

    return () => {
      if (refreshInterval) {
        clearInterval(refreshInterval)
      }
    }
  }, [user, isLoading, silentTokenRefresh])

  // Clean up debounce timer on unmount
  React.useEffect(() => {
    return () => {
      if (authCheckDebounceTimer.current) {
        clearTimeout(authCheckDebounceTimer.current)
      }
    }
  }, [])

  const initializeAuth = useCallback(async () => {
    logger.debug('[AuthContext] initializeAuth called')

    // Prevent multiple simultaneous auth checks
    if (authInitializationInProgress.current) {
      logger.debug(
        '[AuthContext] Auth initialization already in progress, skipping',
      )
      return
    }

    if (sessionManager.isLoginInProgress()) {
      logger.debug(
        '[AuthContext] Skipping auth initialization - login in progress',
      )
      return
    }

    authInitializationInProgress.current = true
    logger.debug('[AuthContext] Starting auth initialization')

    try {
      // IMPORTANT: Clear API cache at the start to ensure fresh data
      // This prevents serving stale user data from cache on page refresh
      apiClient.clearCache()
      logger.debug('[AuthContext] Cleared API cache')

      // Dev auto-login is handled by the inline script in layout.tsx
      // (runs before React hydration, sets the auth cookie).
      // AuthContext just needs to verify the existing session below.

      // Determine if we're on a public route (declare outside try block to avoid scope issues)
      const currentPath =
        typeof window !== 'undefined' ? window.location.pathname : ''
      logger.debug('[AuthContext] Current path:', currentPath)

      const isPublicRoute =
        publicRoutes.includes(currentPath) ||
        currentPath.startsWith('/about') ||
        currentPath.startsWith('/verify-email') ||
        currentPath.startsWith('/accept-invitation') ||
        currentPath.startsWith('/reset-password') ||
        currentPath.startsWith('/activate')

      logger.debug('[AuthContext] Is public route:', isPublicRoute)

      // For public routes, check if we have a token to avoid unnecessary API calls
      const hasToken = false // SECURITY FIX: Removed localStorage token check - cookie-only auth
      const hasAuthVerified =
        typeof window !== 'undefined' && localStorage.getItem('auth_verified')

      logger.debug('[AuthContext] Has auth verified:', hasAuthVerified)

      // Always verify authentication via API for protected routes to ensure cookie session validity
      // For public routes, only skip if we have no auth indicators
      if (isPublicRoute && !hasToken && !hasAuthVerified) {
        logger.debug(
          '[AuthContext] Public route with no auth, clearing user state',
        )
        setUser(null)
        setOrganizations([])
        setIsLoading(false)
        return
      }

      // For protected routes or public routes with auth indicators, always verify via API
      // This ensures HttpOnly cookies are properly validated
      try {
        logger.debug(
          '[AuthContext] Starting API calls to verify authentication',
        )
        // Single API call for user + organizations (with fallback to 2 calls)
        let currentUser: any
        let orgs: any[]
        try {
          logger.debug('[AuthContext] Calling getUserContexts()')
          const contexts = await apiClient.getUserContexts()
          currentUser = contexts.user
          orgs = contexts.organizations
        } catch (ctxError: any) {
          logger.debug(
            '[AuthContext] getUserContexts failed, falling back to separate calls:',
            ctxError.message,
          )
          const results = await Promise.all([
            apiClient.getUser(),
            apiClient.getOrganizations().catch((error: any) => {
              logger.debug(
                '[AuthContext] getOrganizations failed:',
                error.message,
              )
              return []
            }),
          ])
          currentUser = results[0]
          orgs = results[1]
        }

        logger.debug(
          '[AuthContext] API calls completed. User:',
          currentUser?.username,
          'Orgs:',
          orgs.length,
        )

        // Handle user switch detection
        if (currentUser && sessionManager.detectUserSwitch(currentUser)) {
          logger.debug('[AuthContext] User switch detected')
          const lastSessionUser = sessionManager.getLastSessionUserId()
          sessionManager.handleUserSwitch(
            apiClient,
            String(currentUser.id),
            lastSessionUser,
          )
        }

        // Track current session
        if (currentUser) {
          logger.debug('[AuthContext] Tracking user session')
          sessionManager.trackUserSession(currentUser)
        }

        logger.debug('[AuthContext] Setting user and organizations in state')
        setUser(currentUser)
        setOrganizations(orgs)
        // The host the page was opened on (apex or an org subdomain) does
        // not matter: every page shows what the user may see through any
        // membership, so no redirect between hosts takes place.

        logger.debug('[AuthContext] Auth initialization successful')
      } catch (error) {
        // User is not authenticated or session expired
        logger.debug('[AuthContext] Auth verification failed:', error)

        // Don't log authentication errors as they are expected for unauthenticated users
        setUser(null)
        setOrganizations([])

        // Only clear verification if we're sure auth failed
        if (
          error instanceof Error &&
          error.message.includes('Unauthenticated')
        ) {
          logger.debug('[AuthContext] Clearing auth verification')
          sessionManager.clearAuthVerification()
        }
      }
    } catch (error) {
      // Handle any errors that occur during auth initialization
      logger.debug(
        '[AuthContext] Outer catch - error during auth initialization:',
        error,
      )
      setUser(null)
      setOrganizations([])
    } finally {
      logger.debug('[AuthContext] Finally block - setting isLoading to false')
      setIsLoading(false)
      authInitializationInProgress.current = false
    }
  }, [apiClient])

  // Handle hydration and check for existing session using cookies
  useEffect(() => {
    // CRITICAL: Skip auth initialization if login is in progress to prevent race conditions
    if (sessionManager.isLoginInProgress()) {
      logger.debug('Skipping auth initialization - login in progress')
      return
    }

    // Prevent initialization during Fast Refresh if already initialized
    if (hasInitialized.current) {
      return
    }

    // Debounce auth checks - minimum 5 seconds between checks
    const now = Date.now()
    if (now - lastAuthCheckTime.current < 5000) {
      return
    }

    lastAuthCheckTime.current = now
    hasInitialized.current = true

    // Add small delay to ensure DOM is ready and prevent race conditions
    // In development, use longer delay to batch Fast Refresh calls
    const delay = process.env.NODE_ENV === 'development' ? 500 : 100

    // Clear any existing debounce timer
    if (authCheckDebounceTimer.current) {
      clearTimeout(authCheckDebounceTimer.current)
    }

    authCheckDebounceTimer.current = setTimeout(() => {
      initializeAuth()
    }, delay)

    return () => {
      if (authCheckDebounceTimer.current) {
        clearTimeout(authCheckDebounceTimer.current)
      }
    }
  }, [initializeAuth]) // Include initializeAuth to satisfy exhaustive deps

  const refreshOrganizations = useCallback(async () => {
    try {
      const orgs = await apiClient.getOrganizations()
      setOrganizations(orgs)
    } catch (error) {
      // Failed to fetch organizations
      setOrganizations([])
    }
  }, [apiClient])

  const refreshAuth = useCallback(async () => {
    try {
      const currentUser = await apiClient.getUser()
      setUser(currentUser)

      // Also refresh organizations when user is refreshed
      if (currentUser) {
        await refreshOrganizations()
      }
    } catch (error) {
      // If refresh fails, user is no longer authenticated
      setUser(null)
      setOrganizations([])
    }
  }, [apiClient, refreshOrganizations])

  const login = useCallback(
    async (username: string, password: string) => {
      try {
        // Set login in progress flag
        sessionManager.setLoginInProgress(true)

        // Prepare for login - clear old data
        sessionManager.prepareForLogin(apiClient)

        // Login now sets HttpOnly cookie automatically
        const data = await apiClient.login(username, password)

        // CRITICAL: Clear cache again after login to ensure fresh data
        apiClient.clearCache()

        // Track the current user session AFTER successful login
        sessionManager.trackUserSession(data.user)

        // Fetch organizations BEFORE updating user state to prevent dashboard flash
        await refreshOrganizations()

        // The user stays on the host they logged in on; every host shows
        // the same projects.
        setUser(data.user)

        // Clear development helper flags (dead-code-eliminated in production)
        if (process.env.NODE_ENV === 'development') {
          devAuthHelper.clearManualLogout()
        }
      } catch (error) {
        // Check if this is an email verification error (403)
        if (
          error instanceof Error &&
          (error.message.includes('Email verification required') ||
            error.message.includes('403'))
        ) {
          // Redirect to email verification page
          router.push('/verify-email?messageKey=verifyEmailRequired')
          return
        }

        // Other login errors
        throw error
      } finally {
        // Always clear login in progress flag
        sessionManager.setLoginInProgress(false)
      }
    },
    [apiClient, refreshOrganizations, router],
  )

  const logout = useCallback(async () => {
    try {
      // Call logout endpoint to clear HttpOnly cookie
      await apiClient.logout()
    } catch (error) {
      // Continue with logout even if API call fails
    }

    // Clear session and all caches
    sessionManager.clearSession(apiClient)

    // Clear local state
    setUser(null)
    setOrganizations([])

    // Mark manual logout for dev helper (dead-code-eliminated in production)
    if (process.env.NODE_ENV === 'development') {
      devAuthHelper.markManualLogout()
    }

    // Full page navigation to base domain landing page to reset all React state
    // Use getPrivateUrl to strip org subdomain (e.g., benchathon.what-a-benger.net → what-a-benger.net)
    window.location.href = getPrivateUrl('/')
  }, [apiClient])

  const signup = useCallback(
    async (
      username: string,
      email: string,
      name: string,
      password: string,
      profileData?: {
        legal_expertise_level?: string
        german_proficiency?: string
        degree_program_type?: string
        current_semester?: number
        legal_specializations?: string[]
        gender?: string
        age?: number
        job?: string
        years_of_experience?: number
        subjective_competence_civil?: number
        subjective_competence_public?: number
        subjective_competence_criminal?: number
        grade_zwischenpruefung?: number
        grade_vorgeruecktenubung?: number
        grade_first_staatsexamen?: number
        grade_second_staatsexamen?: number
        ati_s_scores?: Record<string, number>
        ptt_a_scores?: Record<string, number>
        ki_experience_scores?: Record<string, number>
        research_data_consent_accepted?: boolean
      },
      invitationToken?: string,
    ) => {
      try {
        // Use API client for signup with profile data and optional invitation token
        const user = await apiClient.signup(
          username,
          email,
          name,
          password,
          profileData,
          invitationToken,
        )

        // If invitation token was provided, user is already verified and added to org
        // Otherwise, redirect to email verification
        if (invitationToken) {
          // Refresh auth to get updated user data (populates the
          // organizations list); the dashboard already shows the inviting
          // organization's projects, no host change needed.
          await initializeAuth()
          useNotificationStore
            .getState()
            .flash(translate('auth.signupComplete'), 'success')
          router.push('/dashboard')
        } else {
          // Regular signup needs email verification
          router.push('/verify-email?messageKey=registrationSuccess')
        }
      } catch (error) {
        // Signup error
        throw error
      }
    },
    [apiClient, router, initializeAuth],
  )

  const updateUser = useCallback((userData: Partial<User>) => {
    setUser((prevUser) => (prevUser ? { ...prevUser, ...userData } : null))
  }, [])

  // Memoize context value to prevent unnecessary re-renders
  const contextValue = useMemo(
    () => ({
      user,
      login,
      signup,
      logout,
      updateUser,
      isLoading,
      refreshAuth,
      apiClient,
      organizations,
      refreshOrganizations,
    }),
    [
      user,
      login,
      signup,
      logout,
      updateUser,
      isLoading,
      refreshAuth,
      apiClient,
      organizations,
      refreshOrganizations,
    ],
  )

  return (
    <AuthContext.Provider value={contextValue}>
      {/*
        Expose the client to descendants via useApiClient() so new call
        sites can thread the API client explicitly instead of importing the
        global singleton. The singleton path stays fully functional for
        everything not yet migrated.
      */}
      <ApiClientContextProvider client={apiClient}>
        {children}
      </ApiClientContextProvider>
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

/**
 * Non-throwing variant for hooks that must work in provider-less mounts
 * (isolated component tests, embeddable widgets). Returns null outside an
 * AuthProvider — callers fall back to their unauthenticated default. Mirrors
 * useOptionalApiClient / useLegalMarkdownSafe.
 */
export function useOptionalAuth() {
  return useContext(AuthContext)
}
