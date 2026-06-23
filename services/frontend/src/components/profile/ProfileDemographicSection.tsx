'use client'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'

import type { ProfileFormData, SetProfileForm } from './types'

interface ProfileDemographicSectionProps {
  profileForm: ProfileFormData
  setProfileForm: SetProfileForm
}

export function ProfileDemographicSection({
  profileForm,
  setProfileForm,
}: ProfileDemographicSectionProps) {
  const { t } = useI18n()

  return (
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
  )
}

export default ProfileDemographicSection
