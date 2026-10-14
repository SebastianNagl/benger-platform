'use client'

import { useI18n } from '@/contexts/I18nContext'

import { useSlot } from '@/lib/extensions/slots'

/**
 * Host route for the LTI exam-binding content picker.
 *
 * LMS instructors land here after launching an unbound activity to pick the
 * exam it should point at. The picker itself (data fetching, selection,
 * link write-back) ships in the proprietary extended package; the
 * open-core platform only provides the route and a graceful fallback,
 * mirroring src/app/projects/[id]/review/page.tsx.
 */
export default function LtiLinkPage() {
  const { t } = useI18n()
  const LtiLinkPicker = useSlot('LtiLinkPicker')

  if (!LtiLinkPicker) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <p className="text-zinc-500 dark:text-zinc-400">
          {t('lti.link.extendedRequired')}
        </p>
      </div>
    )
  }

  // eslint-disable-next-line react-hooks/static-components
  return <LtiLinkPicker />
}
