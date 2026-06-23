/**
 * Organizations Management Page (redirect shell)
 *
 * The organization management UI now lives in the unified admin interface at
 * `/admin/users-organizations`. This route is kept only as a stable redirect
 * for old bookmarks/links: it forwards superadmins to the unified interface and
 * applies the same route-level access control as before (unauthenticated →
 * `/login`, non-superadmin → `/dashboard`).
 */

'use client'

import { useToast } from '@/components/shared/Toast'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export default function OrganizationsPage() {
  const router = useRouter()
  const { user } = useAuth()
  const { t } = useI18n()
  const { addToast } = useToast()

  // Route-level access control + redirect to the unified interface.
  useEffect(() => {
    if (!user) {
      // User not authenticated, redirect to login
      router.push('/login')
      return
    }

    // Only superadmin can reach the organizations management page; regular
    // organization access is handled inside the unified admin interface.
    if (!user.is_superadmin) {
      addToast(t('admin.accessDeniedDesc'), 'error')
      router.push('/dashboard')
      return
    }

    router.push('/admin/users-organizations')
  }, [user, router, addToast, t])

  return null
}
