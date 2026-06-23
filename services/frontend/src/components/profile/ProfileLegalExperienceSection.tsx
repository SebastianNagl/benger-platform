'use client'

import { ChevronDownIcon } from '@heroicons/react/24/outline'

import { GradeInput } from '@/components/shared/GradeInput'
import { LikertScale } from '@/components/shared/LikertScale'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'

import type { ProfileFormData, SetProfileForm } from './types'

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

// Expertise levels that should show job/years_of_experience fields
const JOB_FIELDS_LEVELS = [
  'graduated_no_practice',
  'practicing_lawyer',
  'judge_professor',
]

interface ProfileLegalExperienceSectionProps {
  profileForm: ProfileFormData
  setProfileForm: SetProfileForm
  expanded: boolean
  onToggle: (next: boolean) => void
}

export function ProfileLegalExperienceSection({
  profileForm,
  setProfileForm,
  expanded,
  onToggle,
}: ProfileLegalExperienceSectionProps) {
  const { t } = useI18n()

  return (
    <div className="border-t border-zinc-200 pt-8 dark:border-zinc-700">
      <button
        type="button"
        onClick={() => onToggle(!expanded)}
        className="group flex w-full items-center justify-between text-left"
      >
        <h2 className="text-xl font-semibold text-zinc-900 dark:text-white">
          {t('profile.legalExperience')}
        </h2>
        <div className="inline-flex items-center gap-1.5">
          <span className="text-sm text-zinc-500 dark:text-zinc-400">
            {expanded
              ? t('profile.hideLegalExperience')
              : t('profile.showLegalExperience')}
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
  )
}

export default ProfileLegalExperienceSection
