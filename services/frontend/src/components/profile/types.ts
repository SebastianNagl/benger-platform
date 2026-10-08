// Shared prop types for the profile page section components.
//
// These mirror the shapes used by `src/app/profile/page.tsx`. They are kept
// here (rather than imported from the page) so the section components have no
// import dependency back on the page module.

import type { Dispatch, SetStateAction } from 'react'

import {
  isBundeslandCode,
  type BundeslandCode,
} from '@/lib/profile/bundeslaender'

export interface UserProfile {
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
  // State of the Staatsexamen (two-letter code)
  exam_bundesland?: BundeslandCode
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

export interface ProfileFormData {
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
  // State of the Staatsexamen (two-letter code)
  exam_bundesland?: BundeslandCode
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

export type SetProfileForm = Dispatch<SetStateAction<ProfileFormData>>

/** The editable form state for a loaded profile (the profile page and the
 * extended onboarding modal share it). */
export function profileFormFromProfile(
  profile: Partial<UserProfile> &
    Pick<UserProfile, 'name' | 'email'> & { exam_bundesland?: string | null },
): ProfileFormData {
  return {
    name: profile.name,
    email: profile.email,
    use_pseudonym: profile.use_pseudonym ?? true,
    age: profile.age,
    job: profile.job || '',
    years_of_experience: profile.years_of_experience,
    legal_expertise_level: profile.legal_expertise_level,
    german_proficiency: profile.german_proficiency,
    degree_program_type: profile.degree_program_type,
    current_semester: profile.current_semester,
    exam_bundesland: isBundeslandCode(profile.exam_bundesland)
      ? profile.exam_bundesland
      : undefined,
    gender: profile.gender,
    subjective_competence_civil: profile.subjective_competence_civil,
    subjective_competence_public: profile.subjective_competence_public,
    subjective_competence_criminal: profile.subjective_competence_criminal,
    grade_zwischenpruefung: profile.grade_zwischenpruefung,
    grade_vorgeruecktenubung: profile.grade_vorgeruecktenubung,
    grade_first_staatsexamen: profile.grade_first_staatsexamen,
    grade_second_staatsexamen: profile.grade_second_staatsexamen,
    ati_s_scores: profile.ati_s_scores,
    ptt_a_scores: profile.ptt_a_scores,
    ki_experience_scores: profile.ki_experience_scores,
  }
}

/**
 * A saved profile as a patch for the auth user (`updateUser`). Drops
 * `preferred_ui_mode`: the boot user deliberately never carries it, so
 * merging a stored value from the profile response would switch the shell
 * (student/expert) as a side effect of saving unrelated profile fields.
 */
export function authUserPatchFromProfile<T extends object>(
  profile: T,
): Omit<T, 'preferred_ui_mode'> {
  const { preferred_ui_mode: _ignored, ...rest } = profile as T & {
    preferred_ui_mode?: unknown
  }
  return rest
}
