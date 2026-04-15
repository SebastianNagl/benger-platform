'use client'

import { LegalPageWrapper } from '@/components/layout/LegalPageWrapper'
import { useI18n } from '@/contexts/I18nContext'

export default function ImprintPage() {
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
      titleKey="legal.imprint.title"
      breadcrumbLabel={t('legal.imprint.title')}
      href="/about/imprint"
    >
      <h1>{t('legal.imprint.title')}</h1>

      <p className="lead text-zinc-700 dark:text-zinc-200">
        {t('legal.imprint.lead')}
      </p>

      <h2>{t('legal.imprint.provider')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {formatText(t('legal.imprint.providerInfo'))}
      </p>

      <h2>{t('legal.imprint.contact')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.imprint.contactInfo')}
      </p>

      <h2>{t('legal.imprint.representedBy')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.imprint.representedByInfo')}
      </p>

      <h2>{t('legal.imprint.registration')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.imprint.registrationInfo')}
      </p>

      <h2>{t('legal.imprint.vatId')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.imprint.vatIdInfo')}
      </p>

      <h2>{t('legal.imprint.responsibleForContent')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {formatText(t('legal.imprint.responsibleInfo'))}
      </p>

      <h2>{t('legal.imprint.disclaimer')}</h2>

      <h3>{t('legal.imprint.disclaimerContent')}</h3>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.imprint.disclaimerText')}
      </p>

      <h3>{t('legal.imprint.linksTitle')}</h3>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.imprint.linksText')}
      </p>

      <h3>{t('legal.imprint.copyrightTitle')}</h3>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.imprint.copyrightText')}
      </p>

      <h2>{t('legal.imprint.dataProtection')}</h2>
      <p className="text-zinc-700 dark:text-zinc-200">
        {t('legal.imprint.dataProtectionText')}
      </p>
    </LegalPageWrapper>
  )
}
