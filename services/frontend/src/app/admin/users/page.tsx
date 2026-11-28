'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

/**
 * Legacy address of the platform-wide user list, which now lives in the
 * users tab of /users-organizations.
 */
export default function LegacyAdminUsersPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/users-organizations?tab=users')
  }, [router])

  return null
}
