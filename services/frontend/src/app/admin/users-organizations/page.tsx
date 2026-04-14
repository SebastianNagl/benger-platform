'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect } from 'react'

export default function LegacyAdminUsersOrganizationsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()

  useEffect(() => {
    const tab = searchParams?.get('tab')
    const newUrl = tab
      ? `/users-organizations?tab=${tab}`
      : '/users-organizations'
    router.replace(newUrl)
  }, [router, searchParams])

  return null
}
