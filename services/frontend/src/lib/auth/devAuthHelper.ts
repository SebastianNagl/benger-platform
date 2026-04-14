/**
 * Development Authentication Helper
 *
 * Provides utilities for development-only auth features.
 * Auto-login is handled by the inline script in layout.tsx
 * (runs before React hydration, controlled by NEXT_PUBLIC_DISABLE_AUTO_LOGIN).
 *
 * This module provides manual logout tracking for cross-subdomain cookie management.
 */

import { getCookieDomain } from '@/lib/utils/subdomain'

class DevAuthHelper {
  /**
   * Mark that manual logout occurred.
   * Uses a short-lived cross-subdomain cookie (30s) so the flag survives
   * navigation from org subdomain to base domain on logout.
   */
  markManualLogout(): void {
    if (typeof document === 'undefined') return
    const domain = getCookieDomain()
    const domainAttr = domain ? `domain=${domain}; ` : ''
    document.cookie = `manual_logout=${Date.now()}; ${domainAttr}path=/; max-age=30; SameSite=Lax`
  }

  /**
   * Clear manual logout flag
   */
  clearManualLogout(): void {
    if (typeof document === 'undefined') return
    const domain = getCookieDomain()
    const domainAttr = domain ? `domain=${domain}; ` : ''
    document.cookie = `manual_logout=; ${domainAttr}path=/; max-age=0; SameSite=Lax`
  }
}

export const devAuthHelper = new DevAuthHelper()
