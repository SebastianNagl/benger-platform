'use client'

import { ChevronDownIcon } from '@heroicons/react/24/outline'

import { LikertScale } from '@/components/shared/LikertScale'
import { useI18n } from '@/contexts/I18nContext'

import type { ProfileFormData, SetProfileForm } from './types'

interface ProfileResearchSectionProps {
  profileForm: ProfileFormData
  setProfileForm: SetProfileForm
  expanded: boolean
  onToggle: (next: boolean) => void
}

export function ProfileResearchSection({
  profileForm,
  setProfileForm,
  expanded,
  onToggle,
}: ProfileResearchSectionProps) {
  const { t } = useI18n()

  return (
    <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
      <button
        type="button"
        onClick={() => onToggle(!expanded)}
        className="group flex w-full items-center justify-between text-left"
      >
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
          {t('profile.researchProfile')}
        </h2>
        <div className="inline-flex items-center gap-1.5">
          <span className="text-sm text-zinc-500 dark:text-zinc-400">
            {expanded
              ? t('profile.hideOptionalSettings')
              : t('profile.showOptionalSettings')}
          </span>
          <ChevronDownIcon
            className={`h-4 w-4 opacity-70 transition-transform ${
              expanded ? 'rotate-180' : ''
            }`}
          />
        </div>
      </button>

      {expanded && (
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
  )
}

export default ProfileResearchSection
