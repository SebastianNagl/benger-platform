'use client'

import { useToast } from '@/components/shared/Toast'

import { AuthGuard } from '@/components/auth/AuthGuard'
import { APIKeysModal } from '@/components/modals/APIKeysModal'
import { ChangePasswordModal } from '@/components/modals/ChangePasswordModal'
import { ProfileAccountSection } from '@/components/profile/ProfileAccountSection'
import { ProfileDemographicSection } from '@/components/profile/ProfileDemographicSection'
import { ProfileHistorySection } from '@/components/profile/ProfileHistorySection'
import { ProfileLegalExperienceSection } from '@/components/profile/ProfileLegalExperienceSection'
import { ProfileMandatoryBanners } from '@/components/profile/ProfileMandatoryBanners'
import { ProfilePersonalSection } from '@/components/profile/ProfilePersonalSection'
import { ProfilePrivacySection } from '@/components/profile/ProfilePrivacySection'
import { ProfileResearchSection } from '@/components/profile/ProfileResearchSection'
import type { ProfileFormData, UserProfile } from '@/components/profile/types'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import type {
  MandatoryProfileStatus,
  ProfileHistoryEntry,
} from '@/lib/api/types'
import { useCallback, useEffect, useRef, useState } from 'react'

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

      // Fetch the secondary calls in parallel — `mandatory_profile_status` is
      // independent of `profile_history`, and only the superadmin branch needs
      // history at all. Running them serially used to add two extra round-trips
      // to every profile page load.
      const [statusResult, historyResult] = await Promise.allSettled([
        apiClient.getMandatoryProfileStatus(),
        profileData.is_superadmin
          ? apiClient.getProfileHistory()
          : Promise.resolve(null),
      ])
      if (statusResult.status === 'fulfilled') {
        setMandatoryStatus(statusResult.value)
      }
      if (
        profileData.is_superadmin &&
        historyResult.status === 'fulfilled' &&
        historyResult.value !== null
      ) {
        setProfileHistory(historyResult.value)
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

        <ProfileMandatoryBanners
          mandatoryStatus={mandatoryStatus}
          confirmingProfile={confirmingProfile}
          onConfirm={handleConfirmProfile}
        />

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
            <ProfilePersonalSection
              profile={profile}
              profileForm={profileForm}
              setProfileForm={setProfileForm}
            />

            {/* Demographic Information - moved out of collapsible */}
            <ProfileDemographicSection
              profileForm={profileForm}
              setProfileForm={setProfileForm}
            />

            {/* Legal Experience - Collapsible Section */}
            <ProfileLegalExperienceSection
              profileForm={profileForm}
              setProfileForm={setProfileForm}
              expanded={legalExperienceExpanded}
              onToggle={(next) => {
                setLegalExperienceExpanded(next)
                localStorage.setItem('profile_legal_experience_expanded', String(next))
              }}
            />

            {/* Research Profile - Collapsible Section */}
            <ProfileResearchSection
              profileForm={profileForm}
              setProfileForm={setProfileForm}
              expanded={optionalInfoExpanded}
              onToggle={(next) => {
                setOptionalInfoExpanded(next)
                localStorage.setItem('profile_research_profile_expanded', String(next))
              }}
            />

            {/* Privacy Settings - Collapsible */}
            <ProfilePrivacySection
              profile={profile}
              profileForm={profileForm}
              setProfileForm={setProfileForm}
              expanded={privacySettingsExpanded}
              onToggle={(next) => {
                setPrivacySettingsExpanded(next)
                localStorage.setItem('profile_privacy_settings_expanded', String(next))
              }}
            />

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
              <ProfileHistorySection
                profileHistory={profileHistory}
                expanded={profileHistoryExpanded}
                onToggle={(next) => {
                  setProfileHistoryExpanded(next)
                  localStorage.setItem('profile_history_expanded', String(next))
                }}
              />
            )}

            {/* Account Information */}
            <ProfileAccountSection profile={profile} />
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
