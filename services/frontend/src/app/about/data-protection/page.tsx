'use client'

import { LegalPageWrapper } from '@/components/layout/LegalPageWrapper'
import { useI18n } from '@/contexts/I18nContext'

export default function DataProtectionPage() {
  const { t } = useI18n()

  const formatText = (text: string) => {
    return text.split('\n').map((line, index) => (
      <span key={index}>
        {line}
        {index < text.split('\n').length - 1 && <br />}
      </span>
    ))
  }

  return (
    <LegalPageWrapper
      titleKey="legal.dataProtection.title"
      breadcrumbLabel={t('legal.dataProtection.title')}
      href="/about/data-protection"
    >
      <h1>{t('legal.dataProtection.title')}</h1>

      <p className="lead text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.lead')}
      </p>

      <h2>{t('legal.dataProtection.overview')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.overviewText')}
      </p>

      <h2>{t('legal.dataProtection.controller')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {formatText(t('legal.dataProtection.controllerInfo'))}
      </p>

      <h2>{t('legal.dataProtection.dataProcessing')}</h2>

      <h3>{t('legal.dataProtection.accountData')}</h3>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.accountDataText')}
      </p>

      <h3>{t('legal.dataProtection.usageData')}</h3>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.usageDataText')}
      </p>

      <h3>{t('legal.dataProtection.apiKeys')}</h3>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.apiKeysText')}
      </p>

      <h3>{t('legal.dataProtection.cookies')}</h3>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.cookiesText')}
      </p>

      <h2>{t('legal.dataProtection.dataSharing')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.dataSharingText')}
      </p>

      <h2>{t('legal.dataProtection.dataRetention')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.dataRetentionText')}
      </p>

      <h2>{t('legal.dataProtection.yourRights')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.rightsText')}
      </p>

      <h2>{t('legal.dataProtection.security')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.securityText')}
      </p>

      <h2>{t('legal.dataProtection.contact')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.dataProtection.contactText')}
      </p>
    </LegalPageWrapper>
  )
}
