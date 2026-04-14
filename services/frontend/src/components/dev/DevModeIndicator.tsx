'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/contexts/HydrationContext'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { useMemo, useState } from 'react'

export function DevModeIndicator() {
  const { user } = useAuth()
  const isHydrated = useHydration()
  const [showDetails, setShowDetails] = useState(false)

  // Derive visibility from environment and user state
  const isVisible = useMemo(() => {
    if (!isHydrated) return false
    const isDevAutoAuth = process.env.NODE_ENV === 'development' && process.env.NEXT_PUBLIC_DISABLE_AUTO_LOGIN !== 'true'
    const isLocalhost =
      typeof window !== 'undefined' &&
      (window.location.hostname === 'localhost' ||
        window.location.hostname === '127.0.0.1' ||
        window.location.hostname === 'benger.localhost')
    return isDevAutoAuth && isLocalhost && !!user
  }, [isHydrated, user])

  if (!isVisible) {
    return null
  }

  return (
    <>
      {/* Small badge indicator */}
      <div className="fixed bottom-4 right-4 z-50">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="flex items-center gap-2 rounded-full border border-amber-300 bg-amber-100 px-3 py-1.5 text-xs font-medium text-amber-800 shadow-sm transition-colors duration-200 hover:bg-amber-200 dark:border-amber-700 dark:bg-amber-900/80 dark:text-amber-200 dark:hover:bg-amber-800"
          title="Development mode with auto-authentication enabled"
        >
          <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500 dark:bg-amber-400"></span>
          DEV MODE
        </button>
      </div>

      {/* Details popup (only when clicked) */}
      {showDetails && (
        <div className="fixed bottom-16 right-4 z-50 transition-opacity duration-200">
          <div className="max-w-sm rounded-lg border border-gray-200 bg-white p-4 shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="mb-2 flex items-start justify-between">
              <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                Development Mode Active
              </h3>
              <button
                onClick={() => setShowDetails(false)}
                className="text-gray-400 hover:text-gray-500 dark:text-gray-500 dark:hover:text-gray-400"
                aria-label="Close"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
              <p>
                Auto-authenticated as:{' '}
                <strong className="text-gray-800 dark:text-gray-200">
                  {user?.username}
                </strong>
              </p>
              <p>Email: {user?.email}</p>
              <p>Host: {window.location.hostname}</p>
              <p>Superadmin: {user?.is_superadmin ? 'Yes' : 'No'}</p>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

