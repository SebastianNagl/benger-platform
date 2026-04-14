'use client'

import { LanguageSwitcher, ThemeToggle } from '@/components/layout'
import { Button } from '@/components/shared/Button'
import { LikertScale } from '@/components/shared/LikertScale'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

const TOTAL_STEPS = 5

const EXPERTISE_HIERARCHY = [
  'layperson',
  'law_student',
  'referendar',
  'graduated_no_practice',
  'practicing_lawyer',
  'judge_professor',
]

function getExpertiseIndex(level: string): number {
  return EXPERTISE_HIERARCHY.indexOf(level)
}

export default function RegisterPage() {
  const { user, signup } = useAuth()
  const { t } = useI18n()
  const router = useRouter()

  const [currentStep, setCurrentStep] = useState(1)
  const [formData, setFormData] = useState({
    // Step 1: Account
    username: '',
    email: '',
    name: '',
    password: '',
    confirmPassword: '',
    // Step 2: Legal Background
    legalExpertiseLevel: '',
    germanProficiency: '',
    degreeProgramType: '',
    currentSemester: '',
    // Step 3: Demographics
    gender: '',
    age: '',
    job: '',
    yearsOfExperience: '',
    // Step 4: Competence & Grades
    subjectiveCompetenceCivil: undefined as number | undefined,
    subjectiveCompetencePublic: undefined as number | undefined,
    subjectiveCompetenceCriminal: undefined as number | undefined,
    gradeZwischenpruefung: '',
    gradeVorgeruecktenubung: '',
    gradeFirstStaatsexamen: '',
    gradeSecondStaatsexamen: '',
    // Step 5: Psychometric Scales
    atiSScores: {} as Record<string, number>,
    pttAScores: {} as Record<string, number>,
    kiExperienceScores: {} as Record<string, number>,
  })
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [invitationToken, setInvitationToken] = useState<string | null>(null)
  const [isInvitedUser, setIsInvitedUser] = useState(false)
  const [redirectUrl, setRedirectUrl] = useState<string | null>(null)

  // Options
  const legalExpertiseLevels = [
    { value: 'layperson', label: t('register.expertiseLevel.layperson') },
    { value: 'law_student', label: t('register.expertiseLevel.lawStudent') },
    { value: 'referendar', label: t('register.expertiseLevel.referendar') },
    {
      value: 'graduated_no_practice',
      label: t('register.expertiseLevel.graduatedNoPractice'),
    },
    {
      value: 'practicing_lawyer',
      label: t('register.expertiseLevel.practicingLawyer'),
    },
    {
      value: 'judge_professor',
      label: t('register.expertiseLevel.judgeProfessor'),
    },
  ]

  const germanProficiencyLevels = [
    { value: 'native', label: t('register.germanProficiency.native') },
    { value: 'c2', label: t('register.germanProficiency.c2') },
    { value: 'c1', label: t('register.germanProficiency.c1') },
    { value: 'b2', label: t('register.germanProficiency.b2') },
    { value: 'below_b2', label: t('register.germanProficiency.belowB2') },
  ]

  const degreeProgramTypes = [
    { value: 'staatsexamen', label: t('register.degreeProgram.staatsexamen') },
    { value: 'llb', label: t('register.degreeProgram.llb') },
    { value: 'llm', label: t('register.degreeProgram.llm') },
    { value: 'promotion', label: t('register.degreeProgram.promotion') },
    {
      value: 'not_applicable',
      label: t('register.degreeProgram.notApplicable'),
    },
  ]

  const genderOptions = [
    { value: 'maennlich', label: t('register.gender.male') },
    { value: 'weiblich', label: t('register.gender.female') },
    { value: 'divers', label: t('register.gender.diverse') },
    { value: 'keine_angabe', label: t('register.gender.preferNotToSay') },
  ]

  // Conditional field visibility
  const showDegreeProgramField =
    formData.legalExpertiseLevel !== '' &&
    formData.legalExpertiseLevel !== 'layperson'
  const showSemesterField = formData.legalExpertiseLevel === 'law_student'

  // Grade visibility based on expertise hierarchy
  const expertiseIdx = getExpertiseIndex(formData.legalExpertiseLevel)
  const isIncomparableGradingProgram = formData.degreeProgramType === 'llb' || formData.degreeProgramType === 'llm'
  const showGradeZwischenpruefung = expertiseIdx >= 1 && !isIncomparableGradingProgram // law_student and above, not LLB/LLM
  const showGradeVorgeruecktenubung = expertiseIdx >= 1 && !isIncomparableGradingProgram // law_student and above, not LLB/LLM
  const showGradeFirstStaatsexamen = expertiseIdx >= 2 && !isIncomparableGradingProgram // referendar and above, not LLB/LLM
  const showGradeSecondStaatsexamen = expertiseIdx >= 3 && !isIncomparableGradingProgram // graduated_no_practice and above, not LLB/LLM

  // Step labels
  const stepLabels = [
    t('register.steps.account'),
    t('register.steps.legalBackground'),
    t('register.steps.demographics'),
    t('register.steps.competenceGrades'),
    t('register.steps.psychometricScales'),
  ]

  // Check for invitation token and redirect URL in URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const token = params.get('invitation')
    const email = params.get('email')
    const redirect = params.get('redirect')

    if (token) {
      setInvitationToken(token)
      setIsInvitedUser(true)
      if (email) {
        setFormData((prev) => ({ ...prev, email }))
      }
    }

    if (redirect) {
      setRedirectUrl(redirect)
    }
  }, [])

  // Redirect authenticated users to appropriate page
  useEffect(() => {
    if (user) {
      router.replace(redirectUrl || '/dashboard')
    }
  }, [user, router, redirectUrl])

  // Prevent flash while redirecting
  if (user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white dark:bg-zinc-900">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('register.redirecting')}
          </p>
        </div>
      </div>
    )
  }

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }))
  }

  const handleGenderChange = (value: string) => {
    setFormData((prev) => ({ ...prev, gender: value }))
  }

  const handleLikertChange = (field: string, value: number) => {
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  const handleScoreChange = (
    scaleKey: 'atiSScores' | 'pttAScores' | 'kiExperienceScores',
    itemKey: string,
    value: number
  ) => {
    setFormData((prev) => ({
      ...prev,
      [scaleKey]: {
        ...prev[scaleKey],
        [itemKey]: value,
      },
    }))
  }

  // Per-step validation
  const validateStep = (step: number): string | null => {
    switch (step) {
      case 1: {
        if (!formData.username.trim()) return t('register.usernameRequired')
        if (!formData.email.trim()) return t('register.emailRequired')
        if (!formData.name.trim()) return t('register.nameRequired')
        if (!formData.password || formData.password.length < 6)
          return t('register.passwordTooShort')
        if (formData.password !== formData.confirmPassword)
          return t('register.passwordMismatch')
        return null
      }
      case 2: {
        if (!formData.legalExpertiseLevel)
          return t('register.legalExpertiseLevelRequired')
        if (!formData.germanProficiency)
          return t('register.germanProficiencyRequired')
        return null
      }
      case 3: {
        // Demographics - all optional
        return null
      }
      case 4: {
        if (
          formData.subjectiveCompetenceCivil === undefined ||
          formData.subjectiveCompetencePublic === undefined ||
          formData.subjectiveCompetenceCriminal === undefined
        ) {
          return t('register.competenceRequired')
        }
        return null
      }
      case 5: {
        const atiKeys = ['item_1', 'item_2', 'item_3', 'item_4']
        const pttKeys = ['item_1', 'item_2', 'item_3', 'item_4']
        const kiKeys = ['item_1', 'item_2', 'item_3', 'item_4']
        for (const key of atiKeys) {
          if (formData.atiSScores[key] === undefined)
            return t('register.psychometricRequired')
        }
        for (const key of pttKeys) {
          if (formData.pttAScores[key] === undefined)
            return t('register.psychometricRequired')
        }
        for (const key of kiKeys) {
          if (formData.kiExperienceScores[key] === undefined)
            return t('register.psychometricRequired')
        }
        return null
      }
      default:
        return null
    }
  }

  const handleNext = () => {
    const validationError = validateStep(currentStep)
    if (validationError) {
      setError(validationError)
      return
    }
    setError(null)
    setCurrentStep((prev) => Math.min(prev + 1, TOTAL_STEPS))
  }

  const handleBack = () => {
    setError(null)
    setCurrentStep((prev) => Math.max(prev - 1, 1))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validate final step
    const validationError = validateStep(currentStep)
    if (validationError) {
      setError(validationError)
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      await signup(
        formData.username,
        formData.email,
        formData.name,
        formData.password,
        {
          legal_expertise_level: formData.legalExpertiseLevel,
          german_proficiency: formData.germanProficiency,
          degree_program_type: formData.degreeProgramType || undefined,
          current_semester: formData.currentSemester
            ? parseInt(formData.currentSemester, 10)
            : undefined,
          gender: formData.gender || undefined,
          age: formData.age ? parseInt(formData.age, 10) : undefined,
          job: formData.job || undefined,
          years_of_experience: formData.yearsOfExperience
            ? parseInt(formData.yearsOfExperience, 10)
            : undefined,
          subjective_competence_civil: formData.subjectiveCompetenceCivil,
          subjective_competence_public: formData.subjectiveCompetencePublic,
          subjective_competence_criminal: formData.subjectiveCompetenceCriminal,
          grade_zwischenpruefung: formData.gradeZwischenpruefung
            ? parseFloat(formData.gradeZwischenpruefung.replace(',', '.'))
            : undefined,
          grade_vorgeruecktenubung: formData.gradeVorgeruecktenubung
            ? parseFloat(formData.gradeVorgeruecktenubung.replace(',', '.'))
            : undefined,
          grade_first_staatsexamen: formData.gradeFirstStaatsexamen
            ? parseFloat(formData.gradeFirstStaatsexamen.replace(',', '.'))
            : undefined,
          grade_second_staatsexamen: formData.gradeSecondStaatsexamen
            ? parseFloat(formData.gradeSecondStaatsexamen.replace(',', '.'))
            : undefined,
          ati_s_scores: formData.atiSScores,
          ptt_a_scores: formData.pttAScores,
          ki_experience_scores: formData.kiExperienceScores,
        },
        invitationToken || undefined
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : t('register.registrationFailed'))
    } finally {
      setIsLoading(false)
    }
  }

  const inputClassName =
    'block w-full rounded-md border border-zinc-300 px-3 py-2 text-zinc-900 placeholder-zinc-500 focus:border-emerald-500 focus:outline-none focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400'

  const labelClassName =
    'block text-sm font-medium text-zinc-900 dark:text-white'

  // Step rendering functions

  const renderStep1 = () => (
    <div className="space-y-4" data-testid="register-step-1">
      <div>
        <label htmlFor="name" className={labelClassName}>
          {t('register.name')} *
        </label>
        <div className="mt-1">
          <input
            id="name"
            name="name"
            type="text"
            autoComplete="name"
            required
            value={formData.name}
            onChange={handleChange}
            className={inputClassName}
            placeholder={t('register.namePlaceholder')}
            data-testid="auth-register-name-input"
          />
        </div>
      </div>

      <div>
        <label htmlFor="username" className={labelClassName}>
          {t('register.username')} *
        </label>
        <div className="mt-1">
          <input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            required
            value={formData.username}
            onChange={handleChange}
            className={inputClassName}
            placeholder={t('register.usernamePlaceholder')}
            data-testid="auth-register-username-input"
          />
        </div>
      </div>

      <div>
        <label htmlFor="email" className={labelClassName}>
          {t('register.email')} *
        </label>
        <div className="mt-1">
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={formData.email}
            onChange={handleChange}
            disabled={isInvitedUser}
            className={`${inputClassName}${isInvitedUser ? ' bg-zinc-100 dark:bg-zinc-700 cursor-not-allowed' : ''}`}
            placeholder={t('register.emailPlaceholder')}
            data-testid="auth-register-email-input"
          />
        </div>
      </div>

      <div>
        <label htmlFor="password" className={labelClassName}>
          {t('register.password')} *
        </label>
        <div className="mt-1">
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            required
            value={formData.password}
            onChange={handleChange}
            className={inputClassName}
            placeholder={t('register.passwordPlaceholder')}
            data-testid="auth-register-password-input"
          />
        </div>
      </div>

      <div>
        <label htmlFor="confirmPassword" className={labelClassName}>
          {t('register.confirmPassword')} *
        </label>
        <div className="mt-1">
          <input
            id="confirmPassword"
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            required
            value={formData.confirmPassword}
            onChange={handleChange}
            className={inputClassName}
            placeholder={t('register.confirmPasswordPlaceholder')}
            data-testid="auth-register-confirm-password-input"
          />
        </div>
      </div>
    </div>
  )

  const renderStep2 = () => (
    <div className="space-y-4" data-testid="register-step-2">
      <div>
        <h3 className="text-lg font-medium text-zinc-900 dark:text-white">
          {t('register.legalExpertiseTitle')}
        </h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t('register.legalExpertiseDescription')}
        </p>
      </div>

      <div>
        <label htmlFor="legalExpertiseLevel" className={labelClassName}>
          {t('register.legalExpertiseLevel')} *
        </label>
        <div className="mt-1" data-testid="auth-register-legal-expertise-select">
          <Select
            value={formData.legalExpertiseLevel}
            onValueChange={(v) => setFormData(prev => ({ ...prev, legalExpertiseLevel: v }))}
            displayValue={legalExpertiseLevels.find(l => l.value === formData.legalExpertiseLevel)?.label}
          >
            <SelectTrigger>
              <SelectValue placeholder={t('register.selectOption')} />
            </SelectTrigger>
            <SelectContent>
              {legalExpertiseLevels.map((level) => (
                <SelectItem key={level.value} value={level.value}>
                  {level.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div>
        <label htmlFor="germanProficiency" className={labelClassName}>
          {t('register.germanProficiencyLabel')} *
        </label>
        <div className="mt-1" data-testid="auth-register-german-proficiency-select">
          <Select
            value={formData.germanProficiency}
            onValueChange={(v) => setFormData(prev => ({ ...prev, germanProficiency: v }))}
            displayValue={germanProficiencyLevels.find(l => l.value === formData.germanProficiency)?.label}
          >
            <SelectTrigger>
              <SelectValue placeholder={t('register.selectOption')} />
            </SelectTrigger>
            <SelectContent>
              {germanProficiencyLevels.map((level) => (
                <SelectItem key={level.value} value={level.value}>
                  {level.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {showDegreeProgramField && (
        <div>
          <label htmlFor="degreeProgramType" className={labelClassName}>
            {t('register.degreeProgramType')}
          </label>
          <div className="mt-1" data-testid="auth-register-degree-program-select">
            <Select
              value={formData.degreeProgramType}
              onValueChange={(v) => setFormData(prev => ({ ...prev, degreeProgramType: v }))}
              displayValue={degreeProgramTypes.find(dt => dt.value === formData.degreeProgramType)?.label}
            >
              <SelectTrigger>
                <SelectValue placeholder={t('register.selectOption')} />
              </SelectTrigger>
              <SelectContent>
                {degreeProgramTypes.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}

      {showSemesterField && (
        <div>
          <label htmlFor="currentSemester" className={labelClassName}>
            {t('register.currentSemester')}
          </label>
          <div className="mt-1">
            <input
              type="number"
              id="currentSemester"
              name="currentSemester"
              min="1"
              max="20"
              value={formData.currentSemester}
              onChange={handleChange}
              className={inputClassName}
              placeholder={t('register.currentSemesterPlaceholder')}
              data-testid="auth-register-semester-input"
            />
          </div>
        </div>
      )}
    </div>
  )

  const renderStep3 = () => (
    <div className="space-y-4" data-testid="register-step-3">
      <div>
        <h3 className="text-lg font-medium text-zinc-900 dark:text-white">
          {t('register.steps.demographics')}
        </h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t('register.demographicsDescription')}
        </p>
      </div>

      <div>
        <label className={labelClassName}>{t('register.gender.label')}</label>
        <div className="mt-2 space-y-2" data-testid="register-gender-options">
          {genderOptions.map((option) => (
            <label
              key={option.value}
              className="flex items-center space-x-3 cursor-pointer"
            >
              <input
                type="radio"
                name="gender"
                value={option.value}
                checked={formData.gender === option.value}
                onChange={() => handleGenderChange(option.value)}
                className="h-4 w-4 border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600 dark:bg-zinc-800"
                data-testid={`register-gender-${option.value}`}
              />
              <span className="text-sm text-zinc-700 dark:text-zinc-300">
                {option.label}
              </span>
            </label>
          ))}
        </div>
      </div>

      <div>
        <label htmlFor="age" className={labelClassName}>
          {t('register.ageLabel')}
        </label>
        <div className="mt-1">
          <input
            type="number"
            id="age"
            name="age"
            min="1"
            max="150"
            value={formData.age}
            onChange={handleChange}
            className={inputClassName}
            placeholder={t('register.agePlaceholder')}
            data-testid="register-age-input"
          />
        </div>
      </div>

      <div>
        <label htmlFor="job" className={labelClassName}>
          {t('register.jobLabel')}
        </label>
        <div className="mt-1">
          <input
            type="text"
            id="job"
            name="job"
            value={formData.job}
            onChange={handleChange}
            className={inputClassName}
            placeholder={t('register.jobPlaceholder')}
            data-testid="register-job-input"
          />
        </div>
      </div>

      <div>
        <label htmlFor="yearsOfExperience" className={labelClassName}>
          {t('register.yearsOfExperienceLabel')}
        </label>
        <div className="mt-1">
          <input
            type="number"
            id="yearsOfExperience"
            name="yearsOfExperience"
            min="0"
            max="100"
            value={formData.yearsOfExperience}
            onChange={handleChange}
            className={inputClassName}
            placeholder={t('register.yearsOfExperiencePlaceholder')}
            data-testid="register-years-of-experience-input"
          />
        </div>
      </div>
    </div>
  )

  const renderStep4 = () => (
    <div className="space-y-6" data-testid="register-step-4">
      <div>
        <h3 className="text-lg font-medium text-zinc-900 dark:text-white">
          {t('register.steps.competenceGrades')}
        </h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t('register.competence.description')}
        </p>
      </div>

      <div className="space-y-4">
        <LikertScale
          name="subjectiveCompetenceCivil"
          label={t('register.competence.civil')}
          value={formData.subjectiveCompetenceCivil}
          onChange={(val) =>
            handleLikertChange('subjectiveCompetenceCivil', val)
          }
          required
        />
        <LikertScale
          name="subjectiveCompetencePublic"
          label={t('register.competence.public')}
          value={formData.subjectiveCompetencePublic}
          onChange={(val) =>
            handleLikertChange('subjectiveCompetencePublic', val)
          }
          required
        />
        <LikertScale
          name="subjectiveCompetenceCriminal"
          label={t('register.competence.criminal')}
          value={formData.subjectiveCompetenceCriminal}
          onChange={(val) =>
            handleLikertChange('subjectiveCompetenceCriminal', val)
          }
          required
        />
      </div>

      {(showGradeZwischenpruefung ||
        showGradeVorgeruecktenubung ||
        showGradeFirstStaatsexamen ||
        showGradeSecondStaatsexamen) && (
        <div className="space-y-4 border-t border-zinc-200 pt-4 dark:border-zinc-700">
          <h4 className="text-sm font-medium text-zinc-900 dark:text-white">
            {t('register.grades.title')}
          </h4>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {t('register.grades.description')}
          </p>

          {showGradeZwischenpruefung && (
            <div>
              <label
                htmlFor="gradeZwischenpruefung"
                className={labelClassName}
              >
                {t('register.grades.zwischenpruefung')}
              </label>
              <div className="mt-1">
                <input
                  type="text"
                  inputMode="decimal"
                  id="gradeZwischenpruefung"
                  name="gradeZwischenpruefung"
                  value={formData.gradeZwischenpruefung}
                  onChange={handleChange}
                  className={inputClassName}
                  placeholder="0,00 - 18,00"
                  data-testid="register-grade-zwischenpruefung"
                />
              </div>
            </div>
          )}

          {showGradeVorgeruecktenubung && (
            <div>
              <label
                htmlFor="gradeVorgeruecktenubung"
                className={labelClassName}
              >
                {t('register.grades.vorgeruecktenubung')}
              </label>
              <div className="mt-1">
                <input
                  type="text"
                  inputMode="decimal"
                  id="gradeVorgeruecktenubung"
                  name="gradeVorgeruecktenubung"
                  value={formData.gradeVorgeruecktenubung}
                  onChange={handleChange}
                  className={inputClassName}
                  placeholder="0,00 - 18,00"
                  data-testid="register-grade-vorgeruecktenubung"
                />
              </div>
            </div>
          )}

          {showGradeFirstStaatsexamen && (
            <div>
              <label
                htmlFor="gradeFirstStaatsexamen"
                className={labelClassName}
              >
                {t('register.grades.firstStaatsexamen')}
              </label>
              <div className="mt-1">
                <input
                  type="text"
                  inputMode="decimal"
                  id="gradeFirstStaatsexamen"
                  name="gradeFirstStaatsexamen"
                  value={formData.gradeFirstStaatsexamen}
                  onChange={handleChange}
                  className={inputClassName}
                  placeholder="0,00 - 18,00"
                  data-testid="register-grade-first-staatsexamen"
                />
              </div>
            </div>
          )}

          {showGradeSecondStaatsexamen && (
            <div>
              <label
                htmlFor="gradeSecondStaatsexamen"
                className={labelClassName}
              >
                {t('register.grades.secondStaatsexamen')}
              </label>
              <div className="mt-1">
                <input
                  type="text"
                  inputMode="decimal"
                  id="gradeSecondStaatsexamen"
                  name="gradeSecondStaatsexamen"
                  value={formData.gradeSecondStaatsexamen}
                  onChange={handleChange}
                  className={inputClassName}
                  placeholder="0,00 - 18,00"
                  data-testid="register-grade-second-staatsexamen"
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )

  const renderStep5 = () => (
    <div className="space-y-6" data-testid="register-step-5">
      <div>
        <h3 className="text-lg font-medium text-zinc-900 dark:text-white">
          {t('register.steps.psychometricScales')}
        </h3>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {t('register.psychometricDescription')}
        </p>
      </div>

      {/* ATI-S Scale */}
      <div className="space-y-3">
        <h4 className="text-sm font-semibold text-zinc-900 dark:text-white">
          {t('register.atiS.title')}
        </h4>
        <LikertScale
          name="atiS_item1"
          label={t('register.atiS.item1')}
          value={formData.atiSScores.item_1}
          onChange={(val) => handleScoreChange('atiSScores', 'item_1', val)}
          required
        />
        <LikertScale
          name="atiS_item2"
          label={t('register.atiS.item2')}
          value={formData.atiSScores.item_2}
          onChange={(val) => handleScoreChange('atiSScores', 'item_2', val)}
          required
        />
        <LikertScale
          name="atiS_item3"
          label={t('register.atiS.item3')}
          value={formData.atiSScores.item_3}
          onChange={(val) => handleScoreChange('atiSScores', 'item_3', val)}
          required
        />
        <LikertScale
          name="atiS_item4"
          label={t('register.atiS.item4')}
          value={formData.atiSScores.item_4}
          onChange={(val) => handleScoreChange('atiSScores', 'item_4', val)}
          required
        />
      </div>

      {/* PTT-A Scale */}
      <div className="space-y-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
        <h4 className="text-sm font-semibold text-zinc-900 dark:text-white">
          {t('register.pttA.title')}
        </h4>
        <LikertScale
          name="pttA_item1"
          label={t('register.pttA.item1')}
          value={formData.pttAScores.item_1}
          onChange={(val) => handleScoreChange('pttAScores', 'item_1', val)}
          required
        />
        <LikertScale
          name="pttA_item2"
          label={t('register.pttA.item2')}
          value={formData.pttAScores.item_2}
          onChange={(val) => handleScoreChange('pttAScores', 'item_2', val)}
          required
        />
        <LikertScale
          name="pttA_item3"
          label={t('register.pttA.item3')}
          value={formData.pttAScores.item_3}
          onChange={(val) => handleScoreChange('pttAScores', 'item_3', val)}
          required
        />
        <LikertScale
          name="pttA_item4"
          label={t('register.pttA.item4')}
          value={formData.pttAScores.item_4}
          onChange={(val) => handleScoreChange('pttAScores', 'item_4', val)}
          required
        />
      </div>

      {/* KI-Erfahrung Scale */}
      <div className="space-y-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
        <h4 className="text-sm font-semibold text-zinc-900 dark:text-white">
          {t('register.kiExperience.title')}
        </h4>
        <LikertScale
          name="kiExperience_item1"
          label={t('register.kiExperience.item1')}
          value={formData.kiExperienceScores.item_1}
          onChange={(val) =>
            handleScoreChange('kiExperienceScores', 'item_1', val)
          }
          required
        />
        <LikertScale
          name="kiExperience_item2"
          label={t('register.kiExperience.item2')}
          value={formData.kiExperienceScores.item_2}
          onChange={(val) =>
            handleScoreChange('kiExperienceScores', 'item_2', val)
          }
          required
        />
        <LikertScale
          name="kiExperience_item3"
          label={t('register.kiExperience.item3')}
          value={formData.kiExperienceScores.item_3}
          onChange={(val) =>
            handleScoreChange('kiExperienceScores', 'item_3', val)
          }
          required
        />
        <LikertScale
          name="kiExperience_item4"
          label={t('register.kiExperience.item4')}
          value={formData.kiExperienceScores.item_4}
          onChange={(val) =>
            handleScoreChange('kiExperienceScores', 'item_4', val)
          }
          required
        />
      </div>
    </div>
  )

  const renderCurrentStep = () => {
    switch (currentStep) {
      case 1:
        return renderStep1()
      case 2:
        return renderStep2()
      case 3:
        return renderStep3()
      case 4:
        return renderStep4()
      case 5:
        return renderStep5()
      default:
        return null
    }
  }

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-900">
      {/* Minimal Header */}
      <header className="relative z-10">
        <nav
          className="mx-auto flex max-w-7xl items-center justify-between p-6 lg:px-8"
          aria-label="Global"
        >
          <div className="flex lg:flex-1">
            <Link href="/" className="-m-1.5 p-1.5">
              <span className="sr-only">BenGER</span>
              <div className="flex items-center gap-2 text-xl font-bold text-zinc-900 dark:text-white">
                <span className="text-2xl">🤘</span>
                <span>BenGER</span>
              </div>
            </Link>
          </div>

          <div className="flex items-center gap-4">
            <Link
              href="/"
              className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              {t('register.backToLanding')}
            </Link>
            <div className="ml-4 flex items-center gap-2">
              <LanguageSwitcher />
              <ThemeToggle />
            </div>
          </div>
        </nav>
      </header>

      {/* Main Content */}
      <main className="flex min-h-[calc(100vh-80px)] items-center justify-center px-6 py-12 lg:px-8">
        <div className="w-full max-w-lg space-y-8">
          {/* Header */}
          <div className="text-center">
            <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
              {t('register.title')}
            </h1>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              <Link
                href="/login"
                className="font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
                data-testid="auth-register-login-link"
              >
                {t('register.login')}
              </Link>
            </p>
          </div>

          {/* Invitation Notice */}
          {isInvitedUser && (
            <div className="rounded-md bg-emerald-50 p-4 dark:bg-emerald-900/20">
              <div className="text-sm text-emerald-700 dark:text-emerald-400">
                {t('register.invitationNotice')}
              </div>
            </div>
          )}

          {/* Step Indicator */}
          <div data-testid="register-stepper">
            <div className="flex items-center justify-between">
              {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1).map(
                (step) => {
                  const isCompleted = step < currentStep
                  const isActive = step === currentStep
                  const isClickable = isCompleted || isActive
                  return (
                    <button
                      key={step}
                      type="button"
                      disabled={!isClickable}
                      onClick={() => {
                        if (isClickable) {
                          setError(null)
                          setCurrentStep(step)
                        }
                      }}
                      className={`flex flex-col items-center ${
                        isClickable
                          ? 'cursor-pointer'
                          : 'cursor-default'
                      }`}
                    >
                      <div
                        className={`flex h-8 w-8 items-center justify-center rounded-full border-2 text-xs font-semibold transition-colors ${
                          isCompleted
                            ? 'border-emerald-600 bg-emerald-600 text-white dark:border-emerald-500 dark:bg-emerald-500'
                            : isActive
                              ? 'border-emerald-600 bg-white text-emerald-600 dark:border-emerald-400 dark:bg-zinc-900 dark:text-emerald-400'
                              : 'border-zinc-300 bg-white text-zinc-400 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-500'
                        }`}
                        data-testid={`register-step-indicator-${step}`}
                      >
                        {isCompleted ? (
                          <svg
                            className="h-4 w-4"
                            fill="none"
                            viewBox="0 0 24 24"
                            strokeWidth={2.5}
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="M4.5 12.75l6 6 9-13.5"
                            />
                          </svg>
                        ) : (
                          step
                        )}
                      </div>
                      <span
                        className={`mt-1 hidden text-[10px] leading-tight sm:block ${
                          isActive
                            ? 'font-medium text-emerald-600 dark:text-emerald-400'
                            : 'text-zinc-400 dark:text-zinc-500'
                        }`}
                      >
                        {stepLabels[step - 1]}
                      </span>
                    </button>
                  )
                }
              )}
            </div>
            {/* Mobile step label */}
            <p className="mt-2 text-center text-xs text-zinc-500 dark:text-zinc-400 sm:hidden">
              {t('register.stepOf', {
                current: String(currentStep),
                total: String(TOTAL_STEPS),
              })}{' '}
              - {stepLabels[currentStep - 1]}
            </p>
          </div>

          {/* Registration Form */}
          <form
            onSubmit={handleSubmit}
            className="space-y-6"
            data-testid="auth-register-form"
          >
            {error && (
              <div
                className="rounded-md bg-red-50 p-4 dark:bg-red-900/20"
                data-testid="auth-register-error-message"
              >
                <div className="text-sm text-red-700 dark:text-red-400">
                  {error}
                </div>
              </div>
            )}

            {renderCurrentStep()}

            {/* Navigation Buttons */}
            <div className="flex items-center justify-between gap-3 pt-2">
              {currentStep > 1 ? (
                <Button
                  type="button"
                  onClick={handleBack}
                  className="border border-zinc-300 bg-white px-4 py-2 text-zinc-700 shadow-sm hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                  data-testid="register-back-button"
                >
                  {t('register.stepBack')}
                </Button>
              ) : (
                <div />
              )}

              {currentStep < TOTAL_STEPS ? (
                <Button
                  type="button"
                  onClick={handleNext}
                  className="bg-emerald-600 px-6 py-2 text-white shadow-sm hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900"
                  data-testid="register-next-button"
                >
                  {t('register.stepNext')}
                </Button>
              ) : (
                <Button
                  type="submit"
                  disabled={isLoading}
                  className="bg-emerald-600 px-6 py-2 text-white shadow-sm hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900"
                  data-testid="auth-register-submit-button"
                >
                  {isLoading ? (
                    <div className="flex items-center justify-center">
                      <div className="mr-2 h-4 w-4 animate-spin rounded-full border-b-2 border-white"></div>
                      {t('register.loading')}
                    </div>
                  ) : (
                    t('register.button')
                  )}
                </Button>
              )}
            </div>
          </form>

          {/* Privacy Notice */}
          <div className="text-center text-xs text-zinc-500 dark:text-zinc-400">
            {t('register.terms')}{' '}
            <Link
              href="/about/data-protection"
              className="underline hover:text-zinc-700 dark:hover:text-zinc-300"
            >
              {t('register.privacyLink')}
            </Link>
            {t('register.to')}
          </div>
        </div>
      </main>
    </div>
  )
}
