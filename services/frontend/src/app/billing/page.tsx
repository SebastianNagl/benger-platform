'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'

/**
 * Expert-shell billing page: the same subscription / usage / invoices
 * surface the student shell offers under /student/billing, reachable from
 * the account menu. The student route is host-locked to the student shell,
 * so this sits outside /student. Community edition: nothing registered →
 * a short notice instead of a 404.
 */
export default function BillingPage() {
  const { t } = useI18n()
  const StudentBilling = useSlot('StudentBilling')

  return (
    <ResponsiveContainer>
      <div className="mb-6">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard', 'Dashboard'), href: '/dashboard' },
            { label: t('navigation.billing', 'Abo & Abrechnung') },
          ]}
        />
      </div>
      {StudentBilling ? (
        // eslint-disable-next-line react-hooks/static-components
        <StudentBilling variant="expert" />
      ) : (
        <p className="text-sm text-zinc-500 dark:text-zinc-400" data-testid="billing-unavailable">
          {t('billing.unavailable', 'Abrechnung ist in dieser Edition nicht verfügbar.')}
        </p>
      )}
    </ResponsiveContainer>
  )
}
