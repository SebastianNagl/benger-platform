'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'

interface LegalPageWrapperProps {
  children: React.ReactNode
  titleKey: string
  breadcrumbLabel: string
  href: string
}

export function LegalPageWrapper({
  children,
  titleKey,
  breadcrumbLabel,
  href,
}: LegalPageWrapperProps) {
  const { user } = useAuth()
  const { t } = useI18n()

  // For authenticated users, show full layout with breadcrumb
  if (user) {
    return (
      <ResponsiveContainer size="xl" className="pb-10 pt-8">
        <div className="mb-4">
          <Breadcrumb
            items={[
              { label: t('navigation.dashboard'), href: '/dashboard' },
              { label: breadcrumbLabel, href },
            ]}
          />
        </div>
        <div className="prose prose-zinc max-w-none dark:prose-invert">
          {children}
        </div>
      </ResponsiveContainer>
    )
  }

  // For unauthenticated users, render content directly (MinimalLayout handles wrapper)
  return <>{children}</>
}
