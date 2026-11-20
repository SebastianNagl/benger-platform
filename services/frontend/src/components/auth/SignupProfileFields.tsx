'use client'

/**
 * Signup answers shared by the register wizard and the signup modal: the
 * extended edition's research-data consent, the optional legal-background
 * selects and the payload fields built from them.
 */

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import { hasSlot } from '@/lib/extensions/slots'

/** Ordered from no legal training to the most experienced. */
export const LEGAL_EXPERTISE_LEVELS = [
  { value: 'layperson', labelKey: 'register.expertiseLevel.layperson' },
  { value: 'law_student', labelKey: 'register.expertiseLevel.lawStudent' },
  { value: 'referendar', labelKey: 'register.expertiseLevel.referendar' },
  {
    value: 'graduated_no_practice',
    labelKey: 'register.expertiseLevel.graduatedNoPractice',
  },
  {
    value: 'practicing_lawyer',
    labelKey: 'register.expertiseLevel.practicingLawyer',
  },
  {
    value: 'judge_professor',
    labelKey: 'register.expertiseLevel.judgeProfessor',
  },
] as const

export const GERMAN_PROFICIENCY_LEVELS = [
  { value: 'native', labelKey: 'register.germanProficiency.native' },
  { value: 'c2', labelKey: 'register.germanProficiency.c2' },
  { value: 'c1', labelKey: 'register.germanProficiency.c1' },
  { value: 'b2', labelKey: 'register.germanProficiency.b2' },
  { value: 'below_b2', labelKey: 'register.germanProficiency.belowB2' },
] as const

/**
 * The slot through which the extended edition adds its research-data consent
 * checkbox. When it is registered, the API refuses a signup without consent,
 * so every signup form renders it and requires it. The name is historical:
 * the checkbox once sat on step 5 of the register wizard.
 */
export const RESEARCH_CONSENT_SLOT = 'signup-step5-consent'

/** True when the consent checkbox is shown and still unticked. */
export function isResearchConsentMissing(consent: boolean): boolean {
  return hasSlot(RESEARCH_CONSENT_SLOT) && !consent
}

/** The consent field of a signup request, sent only when the checkbox exists. */
export function researchConsentPayload(consent: boolean) {
  return {
    research_data_consent_accepted: hasSlot(RESEARCH_CONSENT_SLOT)
      ? consent
      : undefined,
  }
}

/**
 * The legal-background fields of a signup request. Both are optional: an
 * unanswered select is left out of the request.
 */
export function legalBackgroundPayload(answers: {
  legalExpertiseLevel: string
  germanProficiency: string
}) {
  return {
    legal_expertise_level: answers.legalExpertiseLevel || undefined,
    german_proficiency: answers.germanProficiency || undefined,
  }
}

interface LegalBackgroundFieldsProps {
  legalExpertiseLevel: string
  germanProficiency: string
  onLegalExpertiseLevelChange: (value: string) => void
  onGermanProficiencyChange: (value: string) => void
  labelClassName: string
  /** Prefix of the selects' test ids, e.g. `auth-register`. */
  testIdPrefix: string
  disabled?: boolean
}

/** The optional legal expertise level and German proficiency selects. */
export function LegalBackgroundFields({
  legalExpertiseLevel,
  germanProficiency,
  onLegalExpertiseLevelChange,
  onGermanProficiencyChange,
  labelClassName,
  testIdPrefix,
  disabled,
}: LegalBackgroundFieldsProps) {
  const { t } = useI18n()

  const fields: {
    id: string
    label: string
    testId: string
    options: readonly { value: string; labelKey: string }[]
    value: string
    onChange: (value: string) => void
  }[] = [
    {
      id: 'legalExpertiseLevel',
      label: t('register.legalExpertiseLevel'),
      testId: `${testIdPrefix}-legal-expertise-select`,
      options: LEGAL_EXPERTISE_LEVELS,
      value: legalExpertiseLevel,
      onChange: onLegalExpertiseLevelChange,
    },
    {
      id: 'germanProficiency',
      label: t('register.germanProficiencyLabel'),
      testId: `${testIdPrefix}-german-proficiency-select`,
      options: GERMAN_PROFICIENCY_LEVELS,
      value: germanProficiency,
      onChange: onGermanProficiencyChange,
    },
  ]

  return (
    <>
      {fields.map((field) => {
        const selected = field.options.find(
          (option) => option.value === field.value,
        )
        return (
          <div key={field.id}>
            <label htmlFor={field.id} className={labelClassName}>
              {field.label}{' '}
              <span className="font-normal text-zinc-500 dark:text-zinc-400">
                {t('register.optionalField')}
              </span>
            </label>
            <div className="mt-1" data-testid={field.testId}>
              <Select
                value={field.value}
                onValueChange={field.onChange}
                disabled={disabled}
                displayValue={selected ? t(selected.labelKey) : undefined}
              >
                <SelectTrigger id={field.id}>
                  <SelectValue placeholder={t('register.selectOption')} />
                </SelectTrigger>
                <SelectContent>
                  {field.options.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {t(option.labelKey)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        )
      })}
    </>
  )
}
