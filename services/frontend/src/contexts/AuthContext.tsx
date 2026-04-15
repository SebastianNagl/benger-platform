'use client'

import apiClientSingleton, { ApiClient, Organization, User } from '@/lib/api'
import { devAuthHelper } from '@/lib/auth/devAuthHelper'
import { logger } from '@/lib/utils/logger'
import { OrganizationManager } from '@/lib/auth/organizationManager'
import { sessionManager } from '@/lib/auth/sessionManager'
import { parseSubdomain, getOrgUrl, getPrivateUrl, getLastOrgSlug, setLastOrgSlug, clearLastOrgSlug } from '@/lib/utils/subdomain'
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
    },
    invitationToken?: string
  ) => Promise<void>
  logout: () => Promise<void>
  updateUser: (userData: Partial<User>) => void
  isLoading: boolean
  refreshAuth: () => Promise<void>
  apiClient: ApiClient
  organizations: Organization[]
  currentOrganization: Organization | null
  setCurrentOrganization: (org: Organization | null) => void
  refreshOrganizations: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [organizations, setOrganizations] = useState<Organization[]>([])
  const [currentOrganization, setCurrentOrganizationState] =
    useState<Organization | null>(null)
  const router = useRouter()

  // Prevent multiple simultaneous auth checks
  const authInitializationInProgress = useRef(false)
  const hasInitialized = useRef(false)
  const lastAuthCheckTime = useRef(0)
  const authCheckDebounceTimer = useRef<NodeJS.Timeout | null>(null)
  const orgSwitchNavigating = useRef(false)

  // Initialize API client and managers with stable references
  const apiClient = useMemo(() => new ApiClient(), [])
  const orgManager = useMemo(() => new OrganizationManager(), [])

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
    const currentPath = typeof window !== 'undefined' ? window.location.pathname : ''
    if (authRedirect.isPublicRoute(currentPath)) {
      logger.debug('Ignoring auth failure - on public route:', currentPath)
      setUser(null)
      setOrganizations([])
      setCurrentOrganizationState(null)
      orgManager.clear()
      return
    }

    // Authentication failed on a protected route — redirect to login
    setUser(null)
    setOrganizations([])
    setCurrentOrganizationState(null)
    orgManager.clear()
    authRedirect.toLogin(router)
  }, [router, orgManager])

  React.useEffect(() => {
    apiClient.setAuthFailureHandler(handleAuthFailure)
  }, [apiClient, handleAuthFailure])

  // Set up organization context provider
  React.useEffect(() => {
    orgManager.setCurrentOrganization(currentOrganization)
  }, [currentOrganization, orgManager])

  React.useEffect(() => {
    const contextProvider = () => orgManager.getOrganizationContext()
    apiClient.setOrganizationContextProvider(contextProvider)
    // Also set on the global singleton used by module-level API clients (projects, etc.)
    apiClientSingleton.setOrganizationContextProvider(contextProvider)
  }, [apiClient, orgManager])

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
        25 * 60 * 1000
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
      logger.debug('[AuthContext] Auth initialization already in progress, skipping')
      return
    }

    if (sessionManager.isLoginInProgress()) {
      logger.debug('[AuthContext] Skipping auth initialization - login in progress')
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
        currentPath.startsWith('/reset-password')

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
          '[AuthContext] Public route with no auth, clearing user state'
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
          '[AuthContext] Starting API calls to verify authentication'
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
            ctxError.message
          )
          const results = await Promise.all([
            apiClient.getUser(),
            apiClient.getOrganizations().catch((error: any) => {
              logger.debug(
                '[AuthContext] getOrganizations failed:',
                error.message
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
          orgs.length
        )

        // Handle user switch detection
        if (currentUser && sessionManager.detectUserSwitch(currentUser)) {
          logger.debug('[AuthContext] User switch detected')
          const lastSessionUser = sessionManager.getLastSessionUserId()
          sessionManager.handleUserSwitch(
            apiClient,
            String(currentUser.id),
            lastSessionUser
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
        orgManager.setOrganizations(orgs)

        // Set org based on subdomain context
        const { orgSlug, isPrivateMode } = parseSubdomain()
        if (orgSlug && orgs.length > 0) {
          const matchedOrg = orgs.find((o: Organization) => o.slug === orgSlug)
          if (matchedOrg) {
            logger.debug('[AuthContext] Setting org from subdomain:', orgSlug)
            setCurrentOrganizationState(matchedOrg)
            orgManager.setCurrentOrganization(matchedOrg)
            // Persist for returning users, but skip if user is switching away
            if (!orgSwitchNavigating.current) {
              setLastOrgSlug(matchedOrg.slug)
            }
          } else {
            // User doesn't have access to this org subdomain
            logger.debug('[AuthContext] No access to org:', orgSlug)
            setCurrentOrganizationState(null)
            orgManager.setCurrentOrganization(null)
            window.location.href = getPrivateUrl()
          }
        } else {
          // Private mode — check if returning user has a last org
          const lastOrgSlug = getLastOrgSlug()
          if (lastOrgSlug && orgs.length > 0) {
            const lastOrg = orgs.find((o: Organization) => o.slug === lastOrgSlug)
            if (lastOrg) {
              logger.debug('[AuthContext] Redirecting returning user to last org:', lastOrgSlug)
              window.location.href = getOrgUrl(lastOrgSlug, window.location.pathname)
              return
            } else {
              // User no longer has access to this org, clear it
              clearLastOrgSlug()
            }
          }
          logger.debug('[AuthContext] Private mode - no org selected')
          setCurrentOrganizationState(null)
          orgManager.setCurrentOrganization(null)
        }

        // Check mandatory profile status on page load (Issue #1206)
        if (currentUser) {
          try {
            const profileStatusPromise =
              apiClient.getMandatoryProfileStatus()
            const timeoutPromise = new Promise<never>((_, reject) =>
              setTimeout(
                () => reject(new Error('Profile status check timeout')),
                5000
              )
            )
            const profileStatus = await Promise.race([
              profileStatusPromise,
              timeoutPromise,
            ])
            if (
              !profileStatus.mandatory_profile_completed ||
              profileStatus.confirmation_due
            ) {
              const currentPath =
                typeof window !== 'undefined' ? window.location.pathname : ''
              // Only redirect if not already on profile or public pages
              if (
                !currentPath.startsWith('/profile') &&
                !publicRoutes.includes(currentPath)
              ) {
                router.push('/profile')
              }
            }
          } catch {
            // If status check fails or times out, continue normally
          }
        }

        logger.debug('[AuthContext] Auth initialization successful')
      } catch (error) {
        // User is not authenticated or session expired
        logger.debug('[AuthContext] Auth verification failed:', error)

        // Don't log authentication errors as they are expected for unauthenticated users
        setUser(null)
        setOrganizations([])
        orgManager.clear()

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
        error
      )
      setUser(null)
      setOrganizations([])
    } finally {
      logger.debug('[AuthContext] Finally block - setting isLoading to false')
      setIsLoading(false)
      authInitializationInProgress.current = false
    }
  }, [apiClient, orgManager, router]) // Remove currentOrganization dependency to prevent circular updates

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

  const refreshOrganizations = useCallback(
    async (userForOrgCheck?: User) => {
      try {
        const orgs = await apiClient.getOrganizations()
        setOrganizations(orgs)
        orgManager.setOrganizations(orgs)

        // Set org based on subdomain context
        const { orgSlug } = parseSubdomain()
        if (orgSlug && orgs.length > 0) {
          const matchedOrg = orgs.find((o: Organization) => o.slug === orgSlug)
          if (matchedOrg) {
            setCurrentOrganizationState(matchedOrg)
            orgManager.setCurrentOrganization(matchedOrg)
          }
        }
        // In private mode, keep currentOrganization as null
      } catch (error) {
        // Failed to fetch organizations
        setOrganizations([])
        orgManager.clear()
      }
    },
    [apiClient, orgManager]
  )

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
      setCurrentOrganizationState(null)
      orgManager.clear()
    }
  }, [apiClient, refreshOrganizations, orgManager])

  const setCurrentOrganization = useCallback(
    (org: Organization | null) => {
      setCurrentOrganizationState(org)
      orgManager.setCurrentOrganization(org)

      // Navigate to the appropriate subdomain
      if (typeof window !== 'undefined') {
        if (org && org.slug) {
          setLastOrgSlug(org.slug)
          const targetUrl = getOrgUrl(org.slug)
          if (!window.location.href.startsWith(targetUrl.split('/').slice(0, 3).join('/'))) {
            orgSwitchNavigating.current = true
            window.location.href = targetUrl
          }
        } else {
          clearLastOrgSlug()
          const targetUrl = getPrivateUrl()
          if (!window.location.href.startsWith(targetUrl.split('/').slice(0, 3).join('/'))) {
            orgSwitchNavigating.current = true
            window.location.href = targetUrl
          }
        }
      }
    },
    [orgManager]
  )

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
        await refreshOrganizations(data.user)

        // Check if we need an org subdomain redirect (before rendering authenticated UI)
        const { orgSlug: currentOrgSlug } = parseSubdomain()
        if (!currentOrgSlug) {
          const lastOrgSlug = getLastOrgSlug()
          if (lastOrgSlug) {
            const orgs = orgManager.getOrganizations()
            const lastOrg = orgs.find((o: Organization) => o.slug === lastOrgSlug)
            if (lastOrg) {
              logger.debug('[AuthContext] Redirecting returning user to last org after login:', lastOrgSlug)
              window.location.href = getOrgUrl(lastOrgSlug, '/dashboard')
              return
            } else {
              clearLastOrgSlug()
            }
          }
        }

        // Only now update local state — org redirect decided, no flash
        setUser(data.user)

        // Check mandatory profile status after login (Issue #1206)
        try {
          const profileStatus = await apiClient.getMandatoryProfileStatus()
          if (
            !profileStatus.mandatory_profile_completed ||
            profileStatus.confirmation_due
          ) {
            router.push('/profile')
            return
          }
        } catch {
          // If status check fails, continue normally
        }

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
    [apiClient, refreshOrganizations, router]
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

    // Clear organization state
    orgManager.clear()

    // Clear local state
    setUser(null)
    setOrganizations([])
    setCurrentOrganizationState(null)

    // Mark manual logout for dev helper (dead-code-eliminated in production)
    if (process.env.NODE_ENV === 'development') {
      devAuthHelper.markManualLogout()
    }

    // Full page navigation to base domain landing page to reset all React state
    // Use getPrivateUrl to strip org subdomain (e.g., benchathon.what-a-benger.net → what-a-benger.net)
    window.location.href = getPrivateUrl('/')
  }, [apiClient, orgManager])

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
      },
      invitationToken?: string
    ) => {
      try {
        // Use API client for signup with profile data and optional invitation token
        const user = await apiClient.signup(
          username,
          email,
          name,
          password,
          profileData,
          invitationToken
        )

        // If invitation token was provided, user is already verified and added to org
        // Otherwise, redirect to email verification
        if (invitationToken) {
          // Refresh auth to get updated user data — populates organizations list
          await initializeAuth()
          // After signup with invitation, redirect to the org subdomain
          const currentOrgs = orgManager.getOrganizations()
          if (currentOrgs.length > 0) {
            window.location.href = getOrgUrl(currentOrgs[0].slug, '/dashboard')
          } else {
            router.push('/dashboard')
          }
        } else {
          // Regular signup needs email verification
          router.push('/verify-email?messageKey=registrationSuccess')
        }
      } catch (error) {
        // Signup error
        throw error
      }
    },
    [apiClient, router, initializeAuth]
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
      currentOrganization,
      setCurrentOrganization,
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
      currentOrganization,
      setCurrentOrganization,
      refreshOrganizations,
    ]
  )

  return (
    <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
