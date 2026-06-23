// Shared prop types for the profile page section components.
//
// These mirror the shapes used by `src/app/profile/page.tsx`. They are kept
// here (rather than imported from the page) so the section components have no
// import dependency back on the page module.

import type { Dispatch, SetStateAction } from 'react'

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
