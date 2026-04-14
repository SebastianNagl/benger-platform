'use client'

import { HeroPattern } from '@/components/shared'
import { useI18n } from '@/contexts/I18nContext'

const sections = [
  { titleKey: 'architecture.sections.overview', id: 'overview' },
  { titleKey: 'architecture.sections.frontend', id: 'frontend' },
  { titleKey: 'architecture.sections.apiGateway', id: 'api-gateway' },
  { titleKey: 'architecture.sections.celeryWorker', id: 'celery-worker' },
  {
    titleKey: 'architecture.sections.nativeAnnotation',
    id: 'native-annotation-system',
  },
  { titleKey: 'architecture.sections.featureFlags', id: 'feature-flags' },
  {
    titleKey: 'architecture.sections.multiOrgSystem',
    id: 'multi-organisation-system',
  },
  {
    titleKey: 'architecture.sections.notificationSystem',
    id: 'notification-system',
  },
  { titleKey: 'architecture.sections.databases', id: 'databases' },
  { titleKey: 'architecture.sections.deployment', id: 'deployment' },
]

// Helper function to render markdown-style bold text
const renderMarkdown = (text: string) => {
  return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
}

export default function ArchitecturePage() {
  const { t } = useI18n()

  return (
    <>
      <HeroPattern />

      <div className="container mx-auto max-w-5xl px-4 pb-10 pt-16">
        <div className="mb-8">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('architecture.title')}
          </h1>
          <p className="lead mt-4 text-lg text-zinc-600 dark:text-zinc-400">
            <span
              dangerouslySetInnerHTML={{
                __html: renderMarkdown(t('architecture.subtitle')),
              }}
            />
          </p>
        </div>

        <div className="space-y-12">
          {/* Overview Section */}
          <section id="overview">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.sections.overview')}
            </h2>

            <div className="overflow-x-auto rounded-lg bg-zinc-50 p-6 font-mono text-sm dark:bg-zinc-900">
              <pre className="text-zinc-800 dark:text-zinc-200">
                {`┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │     │ API Gateway │     │   Workers   │
│(Next.js 15) │────▶│  (FastAPI)  │────▶│  (Celery)   │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       │            ┌─────────────┐            │
       │            │  Traefik    │            │
       └───────────▶│   Proxy     │◀───────────┘
                    └─────────────┘
                           │
       ┌─────────────┬─────────────┬─────────────┐
       ▼             ▼             ▼             ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   Native    │ │  PostgreSQL │ │    Redis    │ │Multi-Org &  │
│ Annotation  │ │ (Database)  │ │(Cache/Queue)│ │Feature Flags│
│   System    │ │             │ │             │ │             │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘`}
              </pre>
            </div>
          </section>

          {/* Frontend Section */}
          <section id="frontend">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.sections.frontend')}
            </h2>
            <p className="text-zinc-700 dark:text-zinc-200">
              <span
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    t('legal.architecture.content.frontendDesc')
                  ),
                }}
              />
            </p>

            <div className="mt-6 space-y-4">
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('architecture.content.frontend.keyFeaturesTitle')}
              </h3>
              <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                {(
                  t('architecture.content.frontend.keyFeatures') as string[]
                ).map((feature, index) => (
                  <li key={index}>{feature}</li>
                ))}
              </ul>
            </div>
          </section>

          {/* API Gateway Section */}
          <section id="api-gateway">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.sections.apiGateway')}
            </h2>
            <p className="mb-4 text-zinc-700 dark:text-zinc-200">
              <span
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    t('legal.architecture.content.apiGatewayDesc')
                  ),
                }}
              />
            </p>

            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('architecture.content.apiGateway.coreComponentsTitle')}
              </h3>
              <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                {(
                  t(
                    'architecture.content.apiGateway.coreComponents'
                  ) as string[]
                ).map((component, index) => (
                  <li key={index}>{component}</li>
                ))}
              </ul>
            </div>
          </section>

          {/* Celery Worker Section */}
          <section id="celery-worker">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.sections.celeryWorker')}
            </h2>
            <p className="mb-6 text-zinc-700 dark:text-zinc-200">
              <span
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    t('legal.architecture.content.celeryWorkerDesc')
                  ),
                }}
              />
            </p>

            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('architecture.content.celeryWorker.workerTasksTitle')}
              </h3>
              <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                {(
                  t('architecture.content.celeryWorker.workerTasks') as string[]
                ).map((task, index) => (
                  <li key={index}>{task}</li>
                ))}
              </ul>
            </div>
          </section>

          {/* Native Annotation System Section */}
          <section id="native-annotation-system">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.content.nativeAnnotation.title')}
            </h2>
            <p className="mb-6 text-zinc-700 dark:text-zinc-200">
              <span
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    t('legal.architecture.content.nativeAnnotationDesc')
                  ),
                }}
              />
            </p>

            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('architecture.content.nativeAnnotation.coreFeaturesTitle')}
              </h3>
              <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                {(
                  t(
                    'architecture.content.nativeAnnotation.coreFeatures'
                  ) as string[]
                ).map((feature, index) => (
                  <li key={index}>{feature}</li>
                ))}
              </ul>

              <h3 className="mt-6 text-lg font-semibold text-zinc-900 dark:text-white">
                {t('architecture.content.nativeAnnotation.performanceTitle')}
              </h3>
              <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                {(
                  t(
                    'architecture.content.nativeAnnotation.performanceImprovements'
                  ) as string[]
                ).map((improvement, index) => (
                  <li key={index}>{improvement}</li>
                ))}
              </ul>
            </div>
          </section>

          {/* Feature Flag System Section */}
          <section id="feature-flags">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.content.featureFlags.title')}
            </h2>
            <p className="mb-6 text-zinc-700 dark:text-zinc-200">
              <span
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    t('legal.architecture.content.featureFlagsDesc')
                  ),
                }}
              />
            </p>

            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('architecture.content.featureFlags.keyCapabilitiesTitle')}
              </h3>
              <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                {(
                  t(
                    'architecture.content.featureFlags.keyCapabilities'
                  ) as string[]
                ).map((capability, index) => (
                  <li key={index}>{capability}</li>
                ))}
              </ul>

              <h3 className="mt-6 text-lg font-semibold text-zinc-900 dark:text-white">
                {t('architecture.content.featureFlags.usagePatternsTitle')}
              </h3>
              <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                {(
                  t(
                    'architecture.content.featureFlags.usagePatterns'
                  ) as string[]
                ).map((pattern, index) => (
                  <li key={index}>{pattern}</li>
                ))}
              </ul>
            </div>
          </section>

          {/* Multi-Organization System Section */}
          <section id="multi-organisation-system">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.sections.multiOrgSystem')}
            </h2>
            <p className="mb-6 text-zinc-700 dark:text-zinc-200">
              <span
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    t('legal.architecture.content.multiOrgDesc')
                  ),
                }}
              />
            </p>

            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('architecture.content.multiOrg.coreFunctionsTitle')}
              </h3>
              <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                {(
                  t('architecture.content.multiOrg.coreFunctions') as string[]
                ).map((func, index) => (
                  <li key={index}>{func}</li>
                ))}
              </ul>
            </div>
          </section>

          {/* Notification System Section */}
          <section id="notification-system">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.sections.notificationSystem')}
            </h2>
            <p className="mb-6 text-zinc-700 dark:text-zinc-200">
              <span
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    t('legal.architecture.content.notificationDesc')
                  ),
                }}
              />
            </p>

            <div className="space-y-4">
              <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('architecture.content.notifications.notificationTypesTitle')}
              </h3>
              <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                {(
                  t(
                    'architecture.content.notifications.notificationTypes'
                  ) as string[]
                ).map((type, index) => (
                  <li key={index}>{type}</li>
                ))}
              </ul>
            </div>
          </section>

          {/* Databases Section */}
          <section id="databases">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.sections.databases')}
            </h2>
            <p className="mb-6 text-zinc-700 dark:text-zinc-200">
              <span
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    t('legal.architecture.content.databasesDesc')
                  ),
                }}
              />
            </p>

            <div className="space-y-6">
              <div>
                <h3 className="mb-3 text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('architecture.content.databases.postgresqlTitle')}
                </h3>
                <p className="mb-3 text-zinc-700 dark:text-zinc-200">
                  {t('architecture.content.databases.postgresqlDesc')}
                </p>
                <ul className="list-inside list-disc space-y-1 text-zinc-700 dark:text-zinc-200">
                  {(
                    t(
                      'architecture.content.databases.postgresqlFeatures'
                    ) as string[]
                  ).map((feature, index) => (
                    <li key={index}>{feature}</li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="mb-3 text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('architecture.content.databases.redisTitle')}
                </h3>
                <p className="mb-3 text-zinc-700 dark:text-zinc-200">
                  {t('architecture.content.databases.redisDesc')}
                </p>
                <ul className="list-inside list-disc space-y-1 text-zinc-700 dark:text-zinc-200">
                  {(
                    t(
                      'architecture.content.databases.redisFeatures'
                    ) as string[]
                  ).map((feature, index) => (
                    <li key={index}>{feature}</li>
                  ))}
                </ul>
              </div>
            </div>
          </section>

          {/* Deployment Section */}
          <section id="deployment">
            <h2 className="mb-6 text-2xl font-bold text-zinc-900 dark:text-white">
              {t('architecture.sections.deployment')}
            </h2>
            <p className="mb-6 text-zinc-700 dark:text-zinc-200">
              <span
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(
                    t('legal.architecture.content.deploymentDesc')
                  ),
                }}
              />
            </p>

            <div className="space-y-6">
              <div>
                <h3 className="mb-3 text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('architecture.content.deployment.developmentTitle')}
                </h3>
                <p className="mb-3 text-zinc-700 dark:text-zinc-200">
                  {t('architecture.content.deployment.developmentDesc')}
                </p>
                <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                  {(
                    t(
                      'architecture.content.deployment.developmentFeatures'
                    ) as string[]
                  ).map((feature, index) => (
                    <li key={index}>{feature}</li>
                  ))}
                </ul>
              </div>

              <div>
                <h3 className="mb-3 text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('architecture.content.deployment.productionTitle')}
                </h3>
                <p className="mb-3 text-zinc-700 dark:text-zinc-200">
                  {t('architecture.content.deployment.productionDesc')}
                </p>
                <ul className="list-inside list-disc space-y-2 text-zinc-700 dark:text-zinc-200">
                  {(
                    t(
                      'architecture.content.deployment.productionFeatures'
                    ) as string[]
                  ).map((feature, index) => (
                    <li key={index}>{feature}</li>
                  ))}
                </ul>
              </div>
            </div>
          </section>
        </div>
      </div>
    </>
  )
}
