'use client'

import { LoginModal } from '@/components/auth/LoginModal'
import { SignupModal } from '@/components/auth/SignupModal'
import { Button } from '@/components/shared/Button'
import { useAuth } from '@/contexts/AuthContext'
import { useFeatureFlags } from '@/contexts/FeatureFlagContext'
import { useHydration } from '@/contexts/HydrationContext'
import { useI18n } from '@/contexts/I18nContext'
import {
  ArrowRightOnRectangleIcon,
  BeakerIcon,
  BellIcon,
  BuildingOfficeIcon,
  CheckIcon,
  ChevronDownIcon,
  UserIcon,
  UsersIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'
import { useEffect, useRef, useState } from 'react'

export function AuthButton() {
  const { user, logout, isLoading, currentOrganization, organizations, setCurrentOrganization } =
    useAuth()
  const { t } = useI18n()
  const { isEnabled } = useFeatureFlags()
  const isClient = useHydration()
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [showSignupModal, setShowSignupModal] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setDropdownOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Show loading state during auth loading
  if (isLoading) {
    return (
      <Button variant="filled" disabled>
        {isClient ? t('common.loading') : 'Loading...'}
      </Button>
    )
  }

  if (user) {
    return (
      <div className="relative" ref={dropdownRef}>
        <button
          onClick={() => setDropdownOpen(!dropdownOpen)}
          className="hover:bg-zinc-900/2.5 inline-flex items-center justify-center gap-2 overflow-hidden rounded-full px-4 py-1.5 text-sm font-medium leading-tight text-zinc-700 ring-1 ring-inset ring-zinc-900/10 transition hover:text-zinc-900 dark:text-zinc-400 dark:ring-white/10 dark:hover:bg-white/5 dark:hover:text-white"
        >
          <span className="hidden sm:block">{user.username}</span>
          <span className="hidden text-xs opacity-70 md:block">
            ({currentOrganization ? currentOrganization.name : t('auth.private')})
          </span>
          <ChevronDownIcon
            className={`h-4 w-4 opacity-70 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`}
          />
        </button>

        {dropdownOpen && (
          <div className="absolute right-0 z-50 mt-2 w-52 rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-800">
            <div className="py-1">
              {/* Profile Section */}
              <Link
                href="/profile"
                className="flex items-center px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
                onClick={() => setDropdownOpen(false)}
              >
                <UserIcon className="mr-3 h-4 w-4" />
                {isClient ? t('auth.profileSettings') : 'Profile Settings'}
              </Link>

              {/* Settings Section */}
              <Link
                href="/settings/notifications"
                className="flex items-center px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
                onClick={() => setDropdownOpen(false)}
              >
                <BellIcon className="mr-3 h-4 w-4" />
                {isClient
                  ? t('auth.notificationSettings')
                  : 'Notification Settings'}
              </Link>

              {/* Org Switcher Section */}
              {organizations.length > 0 && (
                <>
                  <hr className="my-1 border-zinc-200 dark:border-zinc-700" />
                  <div className="px-4 py-1 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                    {t('auth.switchContext')}
                  </div>
                  <button
                    onClick={() => {
                      setDropdownOpen(false)
                      setCurrentOrganization(null)
                    }}
                    className="flex w-full items-center px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
                  >
                    <UserIcon className="mr-3 h-4 w-4" />
                    {t('auth.private')}
                    {!currentOrganization && (
                      <CheckIcon className="ml-auto h-4 w-4 text-amber-600" />
                    )}
                  </button>
                  {organizations.map((org) => (
                    <button
                      key={org.id}
                      onClick={() => {
                        setDropdownOpen(false)
                        setCurrentOrganization(org)
                      }}
                      className="flex w-full items-center px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
                    >
                      <BuildingOfficeIcon className="mr-3 h-4 w-4" />
                      {org.name}
                      {currentOrganization?.id === org.id && (
                        <CheckIcon className="ml-auto h-4 w-4 text-amber-600" />
                      )}
                    </button>
                  ))}
                </>
              )}

              {/* Admin and Organizations Section - accessible to ALL authenticated users */}
              <hr className="my-1 border-zinc-200 dark:border-zinc-700" />
              <Link
                href="/users-organizations"
                className="flex items-center px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
                onClick={() => setDropdownOpen(false)}
              >
                <UsersIcon className="mr-3 h-4 w-4" />
                {isClient
                  ? t('admin.usersOrganizations')
                  : 'Users & Organizations'}
              </Link>
              {/* Feature Flags - superadmins only */}
              {user?.is_superadmin && (
                <Link
                  href="/admin/feature-flags"
                  className="flex items-center px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
                  onClick={() => setDropdownOpen(false)}
                >
                  <BeakerIcon className="mr-3 h-4 w-4" />
                  {isClient ? t('admin.featureFlags') : 'Feature Flags'}
                </Link>
              )}

              <hr className="my-1 border-zinc-200 dark:border-zinc-700" />

              <button
                onClick={() => {
                  setDropdownOpen(false)
                  logout()
                }}
                className="flex w-full items-center px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700"
                data-testid="logout-button"
              >
                <ArrowRightOnRectangleIcon className="mr-3 h-4 w-4" />
                {isClient ? t('auth.signOut') : 'Sign Out'}
              </button>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <>
      <div className="flex gap-2">
        <Button
          onClick={() => setShowLoginModal(true)}
          variant="filled"
          className="text-sm"
        >
          {isClient ? t('auth.signIn') : 'Sign In'}
        </Button>
        <Button variant="filled" onClick={() => setShowSignupModal(true)}>
          {isClient ? t('auth.signUp') : 'Sign up'}
        </Button>
      </div>

      <LoginModal
        isOpen={showLoginModal}
        onClose={() => setShowLoginModal(false)}
      />

      <SignupModal
        isOpen={showSignupModal}
        onClose={() => setShowSignupModal(false)}
      />
    </>
  )
}
