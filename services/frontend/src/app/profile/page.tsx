'use client'

import { ChevronDownIcon } from '@heroicons/react/24/outline'

import { useToast } from '@/components/shared/Toast'

import { AuthGuard } from '@/components/auth/AuthGuard'
import { APIKeysModal } from '@/components/modals/APIKeysModal'
import { ChangePasswordModal } from '@/components/modals/ChangePasswordModal'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { LikertScale } from '@/components/shared/LikertScale'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import type {
  MandatoryProfileStatus,
  ProfileHistoryEntry,
} from '@/lib/api/types'
import { useCallback, useEffect, useRef, useState } from 'react'

interface UserProfile {
  id: string
  username: string
  email: string
  name: string
  is_superadmin: boolean
  is_active: boolean
  created_at?: string
  updated_at?: string
  // Pseudonymization fields (Issue #790)
  pseudonym?: string
  use_pseudonym?: boolean
  // Demographic fields
  age?: number
  job?: string
  years_of_experience?: number
  // Legal expertise fields (Issue #1085 - aligned with signup form and API)
  legal_expertise_level?: string
  german_proficiency?: string
  degree_program_type?: string
  current_semester?: number
  // Gender (Issue #1206)
  gender?: string
  // Subjective competence (Issue #1206)
  subjective_competence_civil?: number
  subjective_competence_public?: number
  subjective_competence_criminal?: number
  // Objective grades (Issue #1206)
  grade_zwischenpruefung?: number
  grade_vorgeruecktenubung?: number
  grade_first_staatsexamen?: number
  grade_second_staatsexamen?: number
  // Psychometric scales (Issue #1206)
  ati_s_scores?: Record<string, number>
  ptt_a_scores?: Record<string, number>
  ki_experience_scores?: Record<string, number>
  // Mandatory profile tracking (Issue #1206)
  mandatory_profile_completed?: boolean
  profile_confirmed_at?: string
}

interface ProfileFormData {
  name: string
  email: string
  // Privacy settings (Issue #790)
  use_pseudonym?: boolean
  // Demographic fields
  age?: number
  job?: string
  years_of_experience?: number
  // Legal expertise fields (Issue #1085 - aligned with signup form and API)
  legal_expertise_level?: string
  german_proficiency?: string
  degree_program_type?: string
  current_semester?: number
  // Gender (Issue #1206)
  gender?: string
  // Subjective competence (Issue #1206)
  subjective_competence_civil?: number
  subjective_competence_public?: number
  subjective_competence_criminal?: number
  // Objective grades (Issue #1206)
  grade_zwischenpruefung?: number
  grade_vorgeruecktenubung?: number
  grade_first_staatsexamen?: number
  grade_second_staatsexamen?: number
  // Psychometric scales (Issue #1206)
  ati_s_scores?: Record<string, number>
  ptt_a_scores?: Record<string, number>
  ki_experience_scores?: Record<string, number>
}

// Expertise levels that should show grade fields
const GRADE_ZWISCHENPRUEFUNG_LEVELS = [
  'law_student',
  'referendar',
  'graduated_no_practice',
  'practicing_lawyer',
  'judge_professor',
]
const GRADE_FIRST_STAATSEXAMEN_LEVELS = [
  'referendar',
  'graduated_no_practice',
  'practicing_lawyer',
  'judge_professor',
]
const GRADE_SECOND_STAATSEXAMEN_LEVELS = [
  'graduated_no_practice',
  'practicing_lawyer',
  'judge_professor',
]

// Grade input component that accepts comma/dot and displays with comma
function GradeInput({
  id,
  name,
  value,
  onChange,
  className,
  placeholder = '0,00 - 18,00',
}: {
  id: string
  name: string
  value: number | undefined
  onChange: (value: number | undefined) => void
  className: string
  placeholder?: string
}) {
  const [rawValue, setRawValue] = useState(() =>
    value != null ? String(value).replace('.', ',') : ''
  )

  // Sync from external value changes (e.g. profile load)
  useEffect(() => {
    const formatted = value != null ? String(value).replace('.', ',') : ''
    setRawValue((prev) => {
      // Only update if the numeric value actually changed
      const prevNum = prev ? parseFloat(prev.replace(',', '.')) : undefined
      if (prevNum === value) return prev
      return formatted
    })
  }, [value])

  return (
    <input
      type="text"
      inputMode="decimal"
      id={id}
      name={name}
      placeholder={placeholder}
      value={rawValue}
      onChange={(e) => {
        const input = e.target.value
        // Allow digits, comma, dot, and empty
        if (input && !/^[\d.,]*$/.test(input)) return
        setRawValue(input)
        // Parse and propagate numeric value
        if (!input) {
          onChange(undefined)
        } else {
          const parsed = parseFloat(input.replace(',', '.'))
          if (!isNaN(parsed)) onChange(parsed)
        }
      }}
      onBlur={() => {
        // Format with comma on blur
        if (rawValue) {
          const parsed = parseFloat(rawValue.replace(',', '.'))
          if (!isNaN(parsed)) {
            setRawValue(String(parsed).replace('.', ','))
          }
        }
      }}
      className={className}
    />
  )
}

// Expertise levels that should show job/years_of_experience fields
const JOB_FIELDS_LEVELS = [
  'graduated_no_practice',
  'practicing_lawyer',
  'judge_professor',
]

export default function ProfilePage() {
  const { user, updateUser, apiClient } = useAuth()
  const { t } = useI18n()
  const { addToast } = useToast()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [profileLoading, setProfileLoading] = useState(false)
  const [legalExperienceExpanded, setLegalExperienceExpanded] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('profile_legal_experience_expanded')
      if (stored !== null) return stored === 'true'
    }
    return true
  })
  const [optionalInfoExpanded, setOptionalInfoExpanded] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('profile_research_profile_expanded')
      if (stored !== null) return stored === 'true'
    }
    return true
  })
  const [privacySettingsExpanded, setPrivacySettingsExpanded] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('profile_privacy_settings_expanded')
      if (stored !== null) return stored === 'true'
    }
    return false // collapsed by default
  })
  const [profileHistoryExpanded, setProfileHistoryExpanded] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('profile_history_expanded')
      if (stored !== null) return stored === 'true'
    }
    return false // collapsed by default
  })

  // Modal state
  const [passwordModalOpen, setPasswordModalOpen] = useState(false)
  const [apiKeysModalOpen, setApiKeysModalOpen] = useState(false)

  // Mandatory profile state (Issue #1206)
  const [mandatoryStatus, setMandatoryStatus] =
    useState<MandatoryProfileStatus | null>(null)
  const [profileHistory, setProfileHistory] = useState<ProfileHistoryEntry[]>(
    []
  )
  const [confirmingProfile, setConfirmingProfile] = useState(false)

  // Ref to skip the loadProfile re-fetch triggered by updateUser after save.
  // Without this, updateUser changes the user ref → useEffect fires → loadProfile
  // overwrites profileForm with the GET response, creating a race condition
  // where user edits made between save and re-fetch completion are lost.
  const skipLoadProfileRef = useRef(false)

  const [profileForm, setProfileForm] = useState<ProfileFormData>({
    name: '',
    email: '',
    use_pseudonym: true,
    age: undefined,
    job: '',
    years_of_experience: undefined,
    // Legal expertise fields (Issue #1085)
    legal_expertise_level: undefined,
    german_proficiency: undefined,
    degree_program_type: undefined,
    current_semester: undefined,
    // Issue #1206 fields
    gender: undefined,
    subjective_competence_civil: undefined,
    subjective_competence_public: undefined,
    subjective_competence_criminal: undefined,
    grade_zwischenpruefung: undefined,
    grade_vorgeruecktenubung: undefined,
    grade_first_staatsexamen: undefined,
    grade_second_staatsexamen: undefined,
    ati_s_scores: undefined,
    ptt_a_scores: undefined,
    ki_experience_scores: undefined,
  })

  const loadProfile = useCallback(async () => {
    try {
      setLoading(true)
      // Clear ALL caches to ensure we get fresh user data - critical for user switches
      apiClient.clearCache()

      // Clear any user-specific caches as well
      if (typeof window !== 'undefined') {
        const previousUserId = localStorage.getItem('benger_last_session_user')
        if (previousUserId && previousUserId !== user?.id) {
          apiClient.clearUserCache(previousUserId)
        }
      }

      // Small delay to ensure cache is cleared and any pending requests complete
      await new Promise((resolve) => setTimeout(resolve, 200))

      const profileData = await apiClient.getProfile()

      // Validate that the profile data matches the current user
      if (user && profileData.id !== user.id) {
        console.error(
          '[POLLUTION PREVENTION v2] Profile data mismatch - user pollution detected!'
        )
        console.error(
          `[POLLUTION PREVENTION v2] Expected user: ${user.id}, Got: ${profileData.id}`
        )

        // Clear all auth data and redirect to login instead of reloading
        if (typeof window !== 'undefined') {
          localStorage.clear()
          sessionStorage.clear()
          // Redirect to login page
          window.location.href = '/login'
        }
        return
      }

      // Auto-collapse sections if user has filled them and no localStorage override
      const hasLegalData = !!(
        profileData.legal_expertise_level &&
        profileData.subjective_competence_civil != null &&
        profileData.subjective_competence_public != null &&
        profileData.subjective_competence_criminal != null
      )
      const hasResearchData = !!(
        profileData.ati_s_scores &&
        profileData.ptt_a_scores &&
        profileData.ki_experience_scores
      )
      if (typeof window !== 'undefined') {
        if (localStorage.getItem('profile_legal_experience_expanded') === null && hasLegalData) {
          setLegalExperienceExpanded(false)
        }
        if (localStorage.getItem('profile_research_profile_expanded') === null && hasResearchData) {
          setOptionalInfoExpanded(false)
        }
      }

      setProfile(profileData)
      setProfileForm({
        name: profileData.name,
        email: profileData.email,
        use_pseudonym: profileData.use_pseudonym ?? true,
        age: profileData.age,
        job: profileData.job || '',
        years_of_experience: profileData.years_of_experience,
        // Legal expertise fields (Issue #1085)
        legal_expertise_level: profileData.legal_expertise_level,
        german_proficiency: profileData.german_proficiency,
        degree_program_type: profileData.degree_program_type,
        current_semester: profileData.current_semester,
        // Issue #1206 fields
        gender: profileData.gender,
        subjective_competence_civil: profileData.subjective_competence_civil,
        subjective_competence_public: profileData.subjective_competence_public,
        subjective_competence_criminal:
          profileData.subjective_competence_criminal,
        grade_zwischenpruefung: profileData.grade_zwischenpruefung,
        grade_vorgeruecktenubung: profileData.grade_vorgeruecktenubung,
        grade_first_staatsexamen: profileData.grade_first_staatsexamen,
        grade_second_staatsexamen: profileData.grade_second_staatsexamen,
        ati_s_scores: profileData.ati_s_scores,
        ptt_a_scores: profileData.ptt_a_scores,
        ki_experience_scores: profileData.ki_experience_scores,
      })

      // Fetch mandatory profile status (Issue #1206)
      try {
        const status = await apiClient.getMandatoryProfileStatus()
        setMandatoryStatus(status)
      } catch {
        // Silently ignore - endpoint may not be available yet
      }

      // For superadmins, also load profile history
      if (profileData.is_superadmin) {
        try {
          const history = await apiClient.getProfileHistory()
          setProfileHistory(history)
        } catch {
          // Silently ignore - endpoint may not be available yet
        }
      }
    } catch (error) {
      console.error('Failed to load profile:', error)
      addToast(t('profile.loadFailed'), 'error')
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t changes on language switch; we don't want to refetch profile data when that happens
  }, [apiClient, user])

  useEffect(() => {
    // Force reload profile when user changes
    if (user?.id) {
      // Skip the re-fetch triggered by updateUser after a save — we already
      // updated profileForm from the PUT response in handleProfileSubmit.
      if (skipLoadProfileRef.current) {
        skipLoadProfileRef.current = false
        return
      }

      // Additional safety check: ensure localStorage user matches context user
      const storedUserId = localStorage.getItem('benger_last_session_user')
      if (storedUserId && storedUserId !== String(user.id)) {
        console.error(
          '[POLLUTION PREVENTION] User ID mismatch detected in profile page!'
        )
        console.error(
          `[POLLUTION PREVENTION] Context user: ${user.id}, Stored user: ${storedUserId}`
        )
        // Clear everything and redirect to login
        localStorage.clear()
        sessionStorage.clear()
        window.location.href = '/login'
        return
      }

      loadProfile()
    } else {
      // Clear profile data if no user
      setProfile(null)
      setMandatoryStatus(null)
      setProfileHistory([])
      setProfileForm({
        name: '',
        email: '',
        age: undefined,
        job: '',
        years_of_experience: undefined,
        // Legal expertise fields (Issue #1085)
        legal_expertise_level: undefined,
        german_proficiency: undefined,
        degree_program_type: undefined,
        current_semester: undefined,
        // Issue #1206 fields
        gender: undefined,
        subjective_competence_civil: undefined,
        subjective_competence_public: undefined,
        subjective_competence_criminal: undefined,
        grade_zwischenpruefung: undefined,
        grade_vorgeruecktenubung: undefined,
        grade_first_staatsexamen: undefined,
        grade_second_staatsexamen: undefined,
        ati_s_scores: undefined,
        ptt_a_scores: undefined,
        ki_experience_scores: undefined,
      })
    }
  }, [user?.id, loadProfile]) // Reload profile when user changes

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      setProfileLoading(true)

      const updatedProfile = await apiClient.updateProfile(profileForm)

      setProfile(updatedProfile)
      // Update profileForm from the response to ensure displayed values match DB
      setProfileForm({
        name: updatedProfile.name,
        email: updatedProfile.email,
        use_pseudonym: updatedProfile.use_pseudonym ?? true,
        age: updatedProfile.age,
        job: updatedProfile.job || '',
        years_of_experience: updatedProfile.years_of_experience,
        legal_expertise_level: updatedProfile.legal_expertise_level,
        german_proficiency: updatedProfile.german_proficiency,
        degree_program_type: updatedProfile.degree_program_type,
        current_semester: updatedProfile.current_semester,
        gender: updatedProfile.gender,
        subjective_competence_civil: updatedProfile.subjective_competence_civil,
        subjective_competence_public: updatedProfile.subjective_competence_public,
        subjective_competence_criminal:
          updatedProfile.subjective_competence_criminal,
        grade_zwischenpruefung: updatedProfile.grade_zwischenpruefung,
        grade_vorgeruecktenubung: updatedProfile.grade_vorgeruecktenubung,
        grade_first_staatsexamen: updatedProfile.grade_first_staatsexamen,
        grade_second_staatsexamen: updatedProfile.grade_second_staatsexamen,
        ati_s_scores: updatedProfile.ati_s_scores,
        ptt_a_scores: updatedProfile.ptt_a_scores,
        ki_experience_scores: updatedProfile.ki_experience_scores,
      })
      // Skip the loadProfile re-fetch that updateUser will trigger
      skipLoadProfileRef.current = true
      updateUser(updatedProfile) // Update the auth context
      addToast(t('profile.updateSuccess'), 'success')

      // Refresh mandatory status after profile update
      try {
        const status = await apiClient.getMandatoryProfileStatus()
        setMandatoryStatus(status)
      } catch {
        // Silently ignore
      }
    } catch (error: unknown) {
      console.error('Failed to update profile:', error)
      const errorMessage =
        error instanceof Error ? error.message : t('profile.updateFailed')
      addToast(errorMessage, 'error')
    } finally {
      setProfileLoading(false)
    }
  }

  const handleConfirmProfile = async () => {
    try {
      setConfirmingProfile(true)
      await apiClient.confirmProfile()
      addToast(t('profile.profileConfirmed'), 'success')
      // Refresh status
      const status = await apiClient.getMandatoryProfileStatus()
      setMandatoryStatus(status)
    } catch (error: unknown) {
      const msg =
        error instanceof Error ? error.message : t('profile.confirmFailed')
      addToast(msg, 'error')
    } finally {
      setConfirmingProfile(false)
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-8">
        <div className="flex h-64 items-center justify-center">
          <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
        </div>
      </div>
    )
  }

  return (
    <AuthGuard>
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
        {/* Breadcrumb */}
        <div className="mb-4">
          <Breadcrumb
            items={[
              {
                label: t('navigation.dashboard'),
                href: '/dashboard',
              },
              { label: t('navigation.profile'), href: '/profile' },
            ]}
          />
        </div>

        {/* Mandatory profile confirmation banner (Issue #1206) */}
        {mandatoryStatus?.confirmation_due && (
          <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-600 dark:bg-amber-900/20">
            <h3 className="font-medium text-amber-800 dark:text-amber-300">
              {t('profile.confirmationDue')}
            </h3>
            <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
              {t('profile.confirmationDueDescription')}
            </p>
            {mandatoryStatus.missing_fields.length > 0 && (
              <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">
                {t('profile.missingFields')}:{' '}
                {mandatoryStatus.missing_fields.join(', ')}
              </p>
            )}
            <Button
              variant="filled"
              className="mt-3"
              disabled={
                confirmingProfile || mandatoryStatus.missing_fields.length > 0
              }
              onClick={handleConfirmProfile}
            >
              {confirmingProfile
                ? t('profile.confirming')
                : t('profile.confirmProfile')}
            </Button>
          </div>
        )}

        {/* Mandatory profile incomplete banner (Issue #1206) */}
        {mandatoryStatus && !mandatoryStatus.mandatory_profile_completed && !mandatoryStatus.confirmation_due && (
          <div className="mb-6 rounded-lg border border-red-300 bg-red-50 p-4 dark:border-red-600 dark:bg-red-900/20">
            <h3 className="font-medium text-red-800 dark:text-red-300">
              {t('profile.mandatoryIncomplete')}
            </h3>
            <p className="mt-1 text-sm text-red-700 dark:text-red-400">
              {t('profile.mandatoryIncompleteDescription')}
            </p>
            {mandatoryStatus.missing_fields.length > 0 && (
              <p className="mt-2 text-sm text-red-700 dark:text-red-400">
                {t('profile.missingFields')}:{' '}
                {mandatoryStatus.missing_fields.join(', ')}
              </p>
            )}
          </div>
        )}

        <div className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
          {/* Header with title and action buttons */}
          <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">
              {t('profile.title')}
            </h1>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                onClick={() => setPasswordModalOpen(true)}
              >
                {t('profile.changePassword')}
              </Button>
              <Button
                variant="outline"
                onClick={() => setApiKeysModalOpen(true)}
              >
                {t('profile.apiKeys')}
              </Button>
            </div>
          </div>

          {/* Profile Form - Single Column Layout */}
          <form onSubmit={handleProfileSubmit} className="space-y-8">
            {/* Personal Information */}
            <div>
              <h2 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                {t('profile.personalInfo')}
              </h2>
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <label
                      htmlFor="username"
                      className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                    >
                      {t('profile.username')}
                    </label>
                    <input
                      type="text"
                      id="username"
                      name="username"
                      value={profile?.username || ''}
                      disabled
                      autoComplete="username"
                      title={t('profile.usernameNote')}
                      className="w-full cursor-not-allowed rounded-full bg-zinc-100 px-4 py-2 text-sm text-zinc-500 ring-1 ring-zinc-900/5 dark:bg-white/5 dark:text-zinc-400 dark:ring-inset dark:ring-white/5"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="role"
                      className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                    >
                      {t('profile.role')}
                    </label>
                    <input
                      type="text"
                      id="role"
                      name="role"
                      value={
                        profile?.is_superadmin
                          ? t('profile.roles.superadmin')
                          : t('profile.roles.user')
                      }
                      disabled
                      autoComplete="organization-title"
                      title={t('profile.roleNote')}
                      className="w-full cursor-not-allowed rounded-full bg-zinc-100 px-4 py-2 text-sm text-zinc-500 ring-1 ring-zinc-900/5 dark:bg-white/5 dark:text-zinc-400 dark:ring-inset dark:ring-white/5"
                    />
                  </div>
                </div>

                <div>
                  <label
                    htmlFor="name"
                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                  >
                    {t('profile.fullName')}
                  </label>
                  <input
                    type="text"
                    id="name"
                    name="name"
                    value={profileForm.name}
                    onChange={(e) =>
                      setProfileForm({
                        ...profileForm,
                        name: e.target.value,
                      })
                    }
                    autoComplete="name"
                    className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                    required
                  />
                </div>

                <div>
                  <label
                    htmlFor="email"
                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                  >
                    {t('profile.emailAddress')}
                  </label>
                  <input
                    type="email"
                    id="email"
                    name="email"
                    value={profileForm.email}
                    onChange={(e) =>
                      setProfileForm({
                        ...profileForm,
                        email: e.target.value,
                      })
                    }
                    autoComplete="email"
                    className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                    required
                  />
                </div>
              </div>
            </div>

            {/* Demographic Information - moved out of collapsible */}
            <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
              <h2 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                {t('profile.demographicInfo')}
              </h2>
              <div className="space-y-4">
                <div>
                  <label
                    htmlFor="age"
                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                  >
                    {t('profile.age')}
                  </label>
                  <input
                    type="number"
                    id="age"
                    name="age"
                    value={profileForm.age ?? ''}
                    onFocus={(e) => e.target.select()}
                    onWheel={(e) => e.currentTarget.blur()}
                    onChange={(e) => {
                      const val = e.target.value
                      const parsed = val ? parseInt(val, 10) : undefined
                      setProfileForm((prev) => ({
                        ...prev,
                        age: parsed,
                      }))
                    }}
                    min="1"
                    max="150"
                    className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                  />
                </div>

                {/* Gender (Issue #1206) */}
                <div>
                  <label
                    htmlFor="gender"
                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                  >
                    {t('profile.gender')}
                  </label>
                  <Select
                    value={profileForm.gender ?? ''}
                    onValueChange={(v) =>
                      setProfileForm({
                        ...profileForm,
                        gender: v || undefined,
                      })
                    }
                    displayValue={
                      profileForm.gender === 'maennlich' ? t('profile.genderOptions.male') :
                      profileForm.gender === 'weiblich' ? t('profile.genderOptions.female') :
                      profileForm.gender === 'divers' ? t('profile.genderOptions.diverse') :
                      profileForm.gender === 'keine_angabe' ? t('profile.genderOptions.preferNotToSay') :
                      undefined
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={t('profile.selectGender')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="maennlich">
                        {t('profile.genderOptions.male')}
                      </SelectItem>
                      <SelectItem value="weiblich">
                        {t('profile.genderOptions.female')}
                      </SelectItem>
                      <SelectItem value="divers">
                        {t('profile.genderOptions.diverse')}
                      </SelectItem>
                      <SelectItem value="keine_angabe">
                        {t('profile.genderOptions.preferNotToSay')}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* German Proficiency */}
                <div>
                  <label
                    htmlFor="german_proficiency"
                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                  >
                    {t('profile.germanProficiency')}
                  </label>
                  <Select
                    value={profileForm.german_proficiency ?? ''}
                    onValueChange={(v) =>
                      setProfileForm({
                        ...profileForm,
                        german_proficiency: v || undefined,
                      })
                    }
                    displayValue={
                      profileForm.german_proficiency === 'native' ? t('register.germanProficiency.native') :
                      profileForm.german_proficiency === 'c2' ? t('register.germanProficiency.c2') :
                      profileForm.german_proficiency === 'c1' ? t('register.germanProficiency.c1') :
                      profileForm.german_proficiency === 'b2' ? t('register.germanProficiency.b2') :
                      profileForm.german_proficiency === 'below_b2' ? t('register.germanProficiency.belowB2') :
                      undefined
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={t('profile.selectGermanProficiency')} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="native">
                        {t('register.germanProficiency.native')}
                      </SelectItem>
                      <SelectItem value="c2">
                        {t('register.germanProficiency.c2')}
                      </SelectItem>
                      <SelectItem value="c1">
                        {t('register.germanProficiency.c1')}
                      </SelectItem>
                      <SelectItem value="b2">
                        {t('register.germanProficiency.b2')}
                      </SelectItem>
                      <SelectItem value="below_b2">
                        {t('register.germanProficiency.belowB2')}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

              </div>
            </div>

            {/* Legal Experience - Collapsible Section */}
            <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
              <button
                type="button"
                onClick={() => {
                  const next = !legalExperienceExpanded
                  setLegalExperienceExpanded(next)
                  localStorage.setItem('profile_legal_experience_expanded', String(next))
                }}
                className="group flex w-full items-center justify-between text-left"
              >
                <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('profile.legalExperience')}
                </h2>
                <div className="inline-flex items-center gap-1.5">
                  <span className="text-sm text-zinc-500 dark:text-zinc-400">
                    {legalExperienceExpanded
                      ? t('profile.hideLegalExperience')
                      : t('profile.showLegalExperience')}
                  </span>
                  <ChevronDownIcon
                    className={`h-4 w-4 opacity-70 transition-transform ${
                      legalExperienceExpanded ? 'rotate-180' : ''
                    }`}
                  />
                </div>
              </button>

              {legalExperienceExpanded && (
                <div className="mt-6 transition-all duration-200 ease-in-out">
                  <div className="mt-8 space-y-8">
                    {/* Legal Expertise */}
                    <div className="space-y-6">
                      <div>
                        <h3 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
                          {t('profile.legalExpertise')}
                        </h3>
                        <div className="space-y-4">
                          {/* Legal Expertise Level */}
                          <div>
                            <label
                              htmlFor="legal_expertise_level"
                              className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                            >
                              {t('profile.legalExpertiseLevel')}
                            </label>
                            <Select
                              value={profileForm.legal_expertise_level ?? ''}
                              onValueChange={(v) =>
                                setProfileForm({
                                  ...profileForm,
                                  legal_expertise_level: v || undefined,
                                })
                              }
                              displayValue={
                                profileForm.legal_expertise_level === 'layperson' ? t('register.expertiseLevel.layperson') :
                                profileForm.legal_expertise_level === 'law_student' ? t('register.expertiseLevel.lawStudent') :
                                profileForm.legal_expertise_level === 'referendar' ? t('register.expertiseLevel.referendar') :
                                profileForm.legal_expertise_level === 'graduated_no_practice' ? t('register.expertiseLevel.graduatedNoPractice') :
                                profileForm.legal_expertise_level === 'practicing_lawyer' ? t('register.expertiseLevel.practicingLawyer') :
                                profileForm.legal_expertise_level === 'judge_professor' ? t('register.expertiseLevel.judgeProfessor') :
                                undefined
                              }
                            >
                              <SelectTrigger>
                                <SelectValue placeholder={t('profile.selectExpertiseLevel')} />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="layperson">
                                  {t('register.expertiseLevel.layperson')}
                                </SelectItem>
                                <SelectItem value="law_student">
                                  {t('register.expertiseLevel.lawStudent')}
                                </SelectItem>
                                <SelectItem value="referendar">
                                  {t('register.expertiseLevel.referendar')}
                                </SelectItem>
                                <SelectItem value="graduated_no_practice">
                                  {t('register.expertiseLevel.graduatedNoPractice')}
                                </SelectItem>
                                <SelectItem value="practicing_lawyer">
                                  {t('register.expertiseLevel.practicingLawyer')}
                                </SelectItem>
                                <SelectItem value="judge_professor">
                                  {t('register.expertiseLevel.judgeProfessor')}
                                </SelectItem>
                              </SelectContent>
                            </Select>
                          </div>

                          {/* Degree Program Type (shown for law students only) */}
                          {profileForm.legal_expertise_level === 'law_student' && (
                              <div>
                                <label
                                  htmlFor="degree_program_type"
                                  className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                                >
                                  {t('profile.degreeProgramType')}
                                </label>
                                <Select
                                  value={profileForm.degree_program_type ?? ''}
                                  onValueChange={(v) =>
                                    setProfileForm({
                                      ...profileForm,
                                      degree_program_type: v || undefined,
                                    })
                                  }
                                  displayValue={
                                    profileForm.degree_program_type === 'staatsexamen' ? t('register.degreeProgram.staatsexamen') :
                                    profileForm.degree_program_type === 'llb' ? t('register.degreeProgram.llb') :
                                    profileForm.degree_program_type === 'llm' ? t('register.degreeProgram.llm') :
                                    profileForm.degree_program_type === 'promotion' ? t('register.degreeProgram.promotion') :
                                    profileForm.degree_program_type === 'not_applicable' ? t('register.degreeProgram.notApplicable') :
                                    undefined
                                  }
                                >
                                  <SelectTrigger>
                                    <SelectValue placeholder={t('profile.selectDegreeProgram')} />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="staatsexamen">
                                      {t('register.degreeProgram.staatsexamen')}
                                    </SelectItem>
                                    <SelectItem value="llb">
                                      {t('register.degreeProgram.llb')}
                                    </SelectItem>
                                    <SelectItem value="llm">
                                      {t('register.degreeProgram.llm')}
                                    </SelectItem>
                                    <SelectItem value="promotion">
                                      {t('register.degreeProgram.promotion')}
                                    </SelectItem>
                                    <SelectItem value="not_applicable">
                                      {t('register.degreeProgram.notApplicable')}
                                    </SelectItem>
                                  </SelectContent>
                                </Select>
                              </div>
                            )}

                          {/* Current Semester (only for law students) */}
                          {profileForm.legal_expertise_level === 'law_student' && (
                            <div>
                              <label
                                htmlFor="current_semester"
                                className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                              >
                                {t('profile.currentSemester')}
                              </label>
                              <input
                                type="number"
                                id="current_semester"
                                name="current_semester"
                                min="1"
                                max="20"
                                value={profileForm.current_semester ?? ''}
                                onFocus={(e) => e.target.select()}
                                onWheel={(e) => e.currentTarget.blur()}
                                onChange={(e) => {
                                  const val = e.target.value
                                  const parsed = val
                                    ? parseInt(val, 10)
                                    : undefined
                                  setProfileForm((prev) => ({
                                    ...prev,
                                    current_semester: parsed,
                                  }))
                                }}
                                placeholder={t('profile.currentSemesterPlaceholder')}
                                className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                              />
                            </div>
                          )}

                          {/* Job & Years of Experience (graduated or above) */}
                          {profileForm.legal_expertise_level &&
                            JOB_FIELDS_LEVELS.includes(profileForm.legal_expertise_level) && (
                            <>
                              <div>
                                <label
                                  htmlFor="job"
                                  className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                                >
                                  {t('profile.job')}
                                </label>
                                <input
                                  type="text"
                                  id="job"
                                  name="job"
                                  value={profileForm.job}
                                  onChange={(e) =>
                                    setProfileForm({
                                      ...profileForm,
                                      job: e.target.value,
                                    })
                                  }
                                  className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                                />
                              </div>

                              <div>
                                <label
                                  htmlFor="years_of_experience"
                                  className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                                >
                                  {t('profile.yearsOfExperience')}
                                </label>
                                <input
                                  type="number"
                                  id="years_of_experience"
                                  name="years_of_experience"
                                  value={profileForm.years_of_experience ?? ''}
                                  onFocus={(e) => e.target.select()}
                                  onWheel={(e) => e.currentTarget.blur()}
                                  onChange={(e) => {
                                    const val = e.target.value
                                    const parsed = val
                                      ? parseInt(val, 10)
                                      : undefined
                                    setProfileForm((prev) => ({
                                      ...prev,
                                      years_of_experience: parsed,
                                    }))
                                  }}
                                  min="0"
                                  max="100"
                                  className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                                />
                              </div>
                            </>
                          )}

                        </div>
                      </div>
                    </div>

                    {/* Grades (Issue #1206 - conditional based on expertise level, hidden for LLB/LLM) */}
                    {profileForm.legal_expertise_level &&
                      GRADE_ZWISCHENPRUEFUNG_LEVELS.includes(
                        profileForm.legal_expertise_level
                      ) &&
                      profileForm.degree_program_type !== 'llb' &&
                      profileForm.degree_program_type !== 'llm' && (
                        <div className="space-y-6">
                          <div>
                            <h3 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
                              {t('profile.gradesTitle')}
                            </h3>
                            <div className="space-y-4">
                              {/* Zwischenpruefung */}
                              {GRADE_ZWISCHENPRUEFUNG_LEVELS.includes(
                                profileForm.legal_expertise_level!
                              ) && (
                                <div>
                                  <label
                                    htmlFor="grade_zwischenpruefung"
                                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                                  >
                                    {t('profile.gradeZwischenpruefung')}
                                  </label>
                                  <GradeInput
                                    id="grade_zwischenpruefung"
                                    name="grade_zwischenpruefung"
                                    value={profileForm.grade_zwischenpruefung}
                                    onChange={(v) =>
                                      setProfileForm({
                                        ...profileForm,
                                        grade_zwischenpruefung: v,
                                      })
                                    }
                                    className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                                  />
                                </div>
                              )}

                              {/* Vorgeruecktenubung */}
                              {GRADE_ZWISCHENPRUEFUNG_LEVELS.includes(
                                profileForm.legal_expertise_level!
                              ) && (
                                <div>
                                  <label
                                    htmlFor="grade_vorgeruecktenubung"
                                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                                  >
                                    {t('profile.gradeVorgeruecktenubung')}
                                  </label>
                                  <GradeInput
                                    id="grade_vorgeruecktenubung"
                                    name="grade_vorgeruecktenubung"
                                    value={profileForm.grade_vorgeruecktenubung}
                                    onChange={(v) =>
                                      setProfileForm({
                                        ...profileForm,
                                        grade_vorgeruecktenubung: v,
                                      })
                                    }
                                    className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                                  />
                                </div>
                              )}

                              {/* First Staatsexamen */}
                              {GRADE_FIRST_STAATSEXAMEN_LEVELS.includes(
                                profileForm.legal_expertise_level!
                              ) && (
                                <div>
                                  <label
                                    htmlFor="grade_first_staatsexamen"
                                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                                  >
                                    {t('profile.gradeFirstStaatsexamen')}
                                  </label>
                                  <GradeInput
                                    id="grade_first_staatsexamen"
                                    name="grade_first_staatsexamen"
                                    value={profileForm.grade_first_staatsexamen}
                                    onChange={(v) =>
                                      setProfileForm({
                                        ...profileForm,
                                        grade_first_staatsexamen: v,
                                      })
                                    }
                                    className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                                  />
                                </div>
                              )}

                              {/* Second Staatsexamen */}
                              {GRADE_SECOND_STAATSEXAMEN_LEVELS.includes(
                                profileForm.legal_expertise_level!
                              ) && (
                                <div>
                                  <label
                                    htmlFor="grade_second_staatsexamen"
                                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                                  >
                                    {t('profile.gradeSecondStaatsexamen')}
                                  </label>
                                  <GradeInput
                                    id="grade_second_staatsexamen"
                                    name="grade_second_staatsexamen"
                                    value={profileForm.grade_second_staatsexamen}
                                    onChange={(v) =>
                                      setProfileForm({
                                        ...profileForm,
                                        grade_second_staatsexamen: v,
                                      })
                                    }
                                    className="w-full rounded-full bg-white px-4 py-2 text-sm text-zinc-900 ring-1 ring-zinc-900/10 transition placeholder:text-zinc-500 hover:ring-zinc-900/20 focus:outline-none focus:ring-2 focus:ring-emerald-500 dark:bg-white/5 dark:text-white dark:ring-inset dark:ring-white/10 dark:placeholder:text-zinc-400 dark:hover:ring-white/20 dark:focus:ring-emerald-400"
                                  />
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                  </div>

                  {/* Subjective Competence (Issue #1206) */}
                  <div className="mt-8">
                    <h3 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
                      {t('profile.subjectiveCompetence')}
                    </h3>
                    <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
                      {t('profile.subjectiveCompetenceDescription')}
                    </p>
                    <div className="space-y-4">
                      <LikertScale
                        name="subjective_competence_civil"
                        label={t('profile.competenceCivil')}
                        value={profileForm.subjective_competence_civil}
                        onChange={(v) =>
                          setProfileForm({
                            ...profileForm,
                            subjective_competence_civil: v,
                          })
                        }
                      />
                      <LikertScale
                        name="subjective_competence_public"
                        label={t('profile.competencePublic')}
                        value={profileForm.subjective_competence_public}
                        onChange={(v) =>
                          setProfileForm({
                            ...profileForm,
                            subjective_competence_public: v,
                          })
                        }
                      />
                      <LikertScale
                        name="subjective_competence_criminal"
                        label={t('profile.competenceCriminal')}
                        value={profileForm.subjective_competence_criminal}
                        onChange={(v) =>
                          setProfileForm({
                            ...profileForm,
                            subjective_competence_criminal: v,
                          })
                        }
                      />
                    </div>
                  </div>

                </div>
              )}
            </div>

            {/* Research Profile - Collapsible Section */}
            <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
              <button
                type="button"
                onClick={() => {
                  const next = !optionalInfoExpanded
                  setOptionalInfoExpanded(next)
                  localStorage.setItem('profile_research_profile_expanded', String(next))
                }}
                className="group flex w-full items-center justify-between text-left"
              >
                <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('profile.researchProfile')}
                </h2>
                <div className="inline-flex items-center gap-1.5">
                  <span className="text-sm text-zinc-500 dark:text-zinc-400">
                    {optionalInfoExpanded
                      ? t('profile.hideOptionalSettings')
                      : t('profile.showOptionalSettings')}
                  </span>
                  <ChevronDownIcon
                    className={`h-4 w-4 opacity-70 transition-transform ${
                      optionalInfoExpanded ? 'rotate-180' : ''
                    }`}
                  />
                </div>
              </button>

              {optionalInfoExpanded && (
                <div className="mt-6 transition-all duration-200 ease-in-out">
                  {/* Psychometric Scales (Issue #1206) */}
                  <div className="mt-8">
                    <h3 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-white">
                      {t('profile.psychometricScales')}
                    </h3>
                    <p className="mb-4 text-sm text-zinc-600 dark:text-zinc-400">
                      {t('profile.psychometricScalesDescription')}
                    </p>
                    <div className="space-y-10">
                      {/* ATI-S */}
                      <div>
                        <h4 className="mb-3 text-base font-medium text-zinc-800 dark:text-zinc-200">
                          {t('profile.atiS.title')}
                        </h4>
                        <div className="space-y-6">
                          <LikertScale
                            name="ati_s_1"
                            label={t('profile.atiS.item1')}
                            value={profileForm.ati_s_scores?.item_1}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ati_s_scores: {
                                  ...(profileForm.ati_s_scores || {}),
                                  item_1: v,
                                },
                              })
                            }
                          />
                          <LikertScale
                            name="ati_s_2"
                            label={t('profile.atiS.item2')}
                            value={profileForm.ati_s_scores?.item_2}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ati_s_scores: {
                                  ...(profileForm.ati_s_scores || {}),
                                  item_2: v,
                                },
                              })
                            }
                          />
                          <LikertScale
                            name="ati_s_3"
                            label={t('profile.atiS.item3')}
                            value={profileForm.ati_s_scores?.item_3}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ati_s_scores: {
                                  ...(profileForm.ati_s_scores || {}),
                                  item_3: v,
                                },
                              })
                            }
                          />
                          <LikertScale
                            name="ati_s_4"
                            label={t('profile.atiS.item4')}
                            value={profileForm.ati_s_scores?.item_4}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ati_s_scores: {
                                  ...(profileForm.ati_s_scores || {}),
                                  item_4: v,
                                },
                              })
                            }
                          />
                        </div>
                      </div>

                      {/* PTT-A */}
                      <div>
                        <h4 className="mb-3 text-base font-medium text-zinc-800 dark:text-zinc-200">
                          {t('profile.pttA.title')}
                        </h4>
                        <div className="space-y-6">
                          <LikertScale
                            name="ptt_a_1"
                            label={t('profile.pttA.item1')}
                            value={profileForm.ptt_a_scores?.item_1}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ptt_a_scores: {
                                  ...(profileForm.ptt_a_scores || {}),
                                  item_1: v,
                                },
                              })
                            }
                          />
                          <LikertScale
                            name="ptt_a_2"
                            label={t('profile.pttA.item2')}
                            value={profileForm.ptt_a_scores?.item_2}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ptt_a_scores: {
                                  ...(profileForm.ptt_a_scores || {}),
                                  item_2: v,
                                },
                              })
                            }
                          />
                          <LikertScale
                            name="ptt_a_3"
                            label={t('profile.pttA.item3')}
                            value={profileForm.ptt_a_scores?.item_3}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ptt_a_scores: {
                                  ...(profileForm.ptt_a_scores || {}),
                                  item_3: v,
                                },
                              })
                            }
                          />
                          <LikertScale
                            name="ptt_a_4"
                            label={t('profile.pttA.item4')}
                            value={profileForm.ptt_a_scores?.item_4}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ptt_a_scores: {
                                  ...(profileForm.ptt_a_scores || {}),
                                  item_4: v,
                                },
                              })
                            }
                          />
                        </div>
                      </div>

                      {/* KI-Erfahrung */}
                      <div>
                        <h4 className="mb-3 text-base font-medium text-zinc-800 dark:text-zinc-200">
                          {t('profile.kiExperience.title')}
                        </h4>
                        <div className="space-y-6">
                          <LikertScale
                            name="ki_experience_1"
                            label={t('profile.kiExperience.item1')}
                            value={profileForm.ki_experience_scores?.item_1}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ki_experience_scores: {
                                  ...(profileForm.ki_experience_scores || {}),
                                  item_1: v,
                                },
                              })
                            }
                          />
                          <LikertScale
                            name="ki_experience_2"
                            label={t('profile.kiExperience.item2')}
                            value={profileForm.ki_experience_scores?.item_2}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ki_experience_scores: {
                                  ...(profileForm.ki_experience_scores || {}),
                                  item_2: v,
                                },
                              })
                            }
                          />
                          <LikertScale
                            name="ki_experience_3"
                            label={t('profile.kiExperience.item3')}
                            value={profileForm.ki_experience_scores?.item_3}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ki_experience_scores: {
                                  ...(profileForm.ki_experience_scores || {}),
                                  item_3: v,
                                },
                              })
                            }
                          />
                          <LikertScale
                            name="ki_experience_4"
                            label={t('profile.kiExperience.item4')}
                            value={profileForm.ki_experience_scores?.item_4}
                            onChange={(v) =>
                              setProfileForm({
                                ...profileForm,
                                ki_experience_scores: {
                                  ...(profileForm.ki_experience_scores || {}),
                                  item_4: v,
                                },
                              })
                            }
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Privacy Settings - Collapsible */}
            <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
              <button
                type="button"
                onClick={() => {
                  const next = !privacySettingsExpanded
                  setPrivacySettingsExpanded(next)
                  localStorage.setItem('profile_privacy_settings_expanded', String(next))
                }}
                className="group flex w-full items-center justify-between text-left"
              >
                <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
                  {t('profile.privacySettings')}
                </h2>
                <div className="inline-flex items-center gap-1.5">
                  <span className="text-sm text-zinc-500 dark:text-zinc-400">
                    {privacySettingsExpanded
                      ? t('profile.hidePrivacySettings')
                      : t('profile.showPrivacySettings')}
                  </span>
                  <ChevronDownIcon
                    className={`h-4 w-4 opacity-70 transition-transform ${
                      privacySettingsExpanded ? 'rotate-180' : ''
                    }`}
                  />
                </div>
              </button>

              {privacySettingsExpanded && (
              <div className="mt-6 space-y-4 rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50">
                <div>
                  <label
                    htmlFor="pseudonym"
                    className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
                  >
                    {t('profile.yourPseudonym')}
                  </label>
                  <input
                    type="text"
                    id="pseudonym"
                    name="pseudonym"
                    value={profile?.pseudonym || ''}
                    disabled
                    className="w-full rounded-full bg-zinc-100 px-4 py-2 text-sm text-zinc-500 ring-1 ring-zinc-900/5 dark:bg-white/5 dark:text-zinc-400 dark:ring-inset dark:ring-white/5"
                  />
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {t('profile.pseudonymNote')}
                  </p>
                </div>

                <div className="flex items-start">
                  <div className="flex h-5 items-center">
                    <input
                      type="checkbox"
                      id="use_pseudonym"
                      name="use_pseudonym"
                      checked={profileForm.use_pseudonym ?? true}
                      onChange={(e) =>
                        setProfileForm({
                          ...profileForm,
                          use_pseudonym: e.target.checked,
                        })
                      }
                      className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-700 dark:ring-offset-zinc-900"
                    />
                  </div>
                  <div className="ml-3">
                    <label
                      htmlFor="use_pseudonym"
                      className="text-sm font-medium text-zinc-700 dark:text-zinc-300"
                    >
                      {t('profile.usePseudonym')}
                    </label>
                    <p className="text-xs text-zinc-500 dark:text-zinc-400">
                      {t('profile.usePseudonymDescription')}
                    </p>
                  </div>
                </div>
              </div>
              )}
            </div>

            {/* Profile Update Button */}
            <div className="flex justify-start border-t border-zinc-200 pt-8 dark:border-zinc-700">
              <Button
                type="submit"
                variant="filled"
                disabled={profileLoading}
                className="w-full px-8 py-2 lg:w-auto"
              >
                {profileLoading
                  ? t('profile.updating')
                  : t('profile.updateProfile')}
              </Button>
            </div>

            {/* Profile History - Collapsible (superadmin only, Issue #1206) */}
            {profile?.is_superadmin && profileHistory.length > 0 && (
              <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
                <button
                  type="button"
                  onClick={() => {
                    const next = !profileHistoryExpanded
                    setProfileHistoryExpanded(next)
                    localStorage.setItem('profile_history_expanded', String(next))
                  }}
                  className="group flex w-full items-center justify-between text-left"
                >
                  <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
                    {t('profile.profileHistory')}
                  </h2>
                  <div className="inline-flex items-center gap-1.5">
                    <span className="text-sm text-zinc-500 dark:text-zinc-400">
                      {profileHistoryExpanded
                        ? t('profile.hideProfileHistory')
                        : t('profile.showProfileHistory')}
                    </span>
                    <ChevronDownIcon
                      className={`h-4 w-4 opacity-70 transition-transform ${
                        profileHistoryExpanded ? 'rotate-180' : ''
                      }`}
                    />
                  </div>
                </button>

                {profileHistoryExpanded && (
                  <div className="mt-6 space-y-3">
                    {profileHistory.map((entry) => (
                      <div
                        key={entry.id}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/50"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                            {entry.change_type}
                          </span>
                          <span className="text-xs text-zinc-500 dark:text-zinc-400">
                            {new Date(entry.changed_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                          {t('profile.changedFields')}:{' '}
                          {entry.changed_fields.join(', ')}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Account Information */}
            <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
              <h2 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                {t('profile.accountInfo')}
              </h2>
              <div className="space-y-3 text-sm text-zinc-600 dark:text-zinc-400">
                {profile?.created_at && (
                  <div>
                    <span className="font-medium">
                      {t('profile.memberSince')}
                    </span>{' '}
                    {new Date(profile.created_at).toLocaleDateString()}
                  </div>
                )}
                {profile?.updated_at && (
                  <div>
                    <span className="font-medium">
                      {t('profile.lastUpdated')}
                    </span>{' '}
                    {new Date(profile.updated_at).toLocaleDateString()}
                  </div>
                )}
                {profile?.profile_confirmed_at && (
                  <div>
                    <span className="font-medium">
                      {t('profile.lastConfirmed')}
                    </span>{' '}
                    {new Date(
                      profile.profile_confirmed_at
                    ).toLocaleDateString()}
                  </div>
                )}
              </div>
            </div>
          </form>
        </div>

        {/* Modals */}
        <ChangePasswordModal
          isOpen={passwordModalOpen}
          onClose={() => setPasswordModalOpen(false)}
        />
        <APIKeysModal
          isOpen={apiKeysModalOpen}
          onClose={() => setApiKeysModalOpen(false)}
        />
      </ResponsiveContainer>
    </AuthGuard>
  )
}
