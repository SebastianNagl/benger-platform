'use client'

import { Alert } from '@/components/shared/Alert'
import { CloudImportPanel } from '@/components/projects/import/CloudImportPanel'
import { ImportSourceTabs } from '@/components/projects/import/ImportSourceTabs'
import { useSlot } from '@/lib/extensions/slots'
import { useI18n } from '@/contexts/I18nContext'

interface StepDataImportProps {
  pastedData: string
  selectedFile: File | null
  dataColumns: string[]
  onPastedDataChange: (data: string) => void
  onFileChange: (file: File | null) => void
  onDataColumnsChange: (columns: string[]) => void
  /** The synthetic generator feature is active: uploads join generated rows
   *  and must follow their structure — a warning box says so. */
  syntheticActive?: boolean
  /** Column structure of the already-present synthetic rows (shown as chips
   *  in the warning when known). */
  syntheticColumns?: string[]
  /** Full wizard state + updater — passed through to the extended
   *  structured-exam tab (ProjectWizardStructuredEntry slot). */
  wizardData?: Record<string, any>
  onWizardChange?: (partial: Record<string, any>) => void
}

export function StepDataImport({
  pastedData,
  selectedFile,
  dataColumns,
  onPastedDataChange,
  onFileChange,
  onDataColumnsChange,
  syntheticActive = false,
  syntheticColumns = [],
  wizardData,
  onWizardChange,
}: StepDataImportProps) {
  const { t } = useI18n()
  // Extended: structured Klausur entry as an additional tab. Ordered first
  // for exam-type projects so the natural flow lands on the typed part editor.
  const StructuredEntry = useSlot('ProjectWizardStructuredEntry')
  // Hidden on deck-type projects: applying an exam there would silently
  // overwrite the flashcard labeling config.
  const hasStructuredTab = !!(
    StructuredEntry &&
    wizardData &&
    onWizardChange &&
    wizardData.projectKind !== 'flashcard_collection'
  )

  return (
    <div className="space-y-6">
      <div>
        <h2 className="mb-2 text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('projects.creation.wizard.step2.title')}
        </h2>
        <p className="text-zinc-600 dark:text-zinc-400">
          {t('projects.creation.wizard.step2.subtitle')}
        </p>
      </div>

      {syntheticActive && (
        <div data-testid="step2-synthetic-warning">
          <Alert variant="warning">
            <span>
              {t('projects.creation.wizard.step2.syntheticNotice')}
              {syntheticColumns.length > 0 && (
                <>
                  {' '}
                  {t('projects.creation.wizard.step2.syntheticNoticeColumns')}{' '}
                  <span className="inline-flex flex-wrap gap-1 align-middle">
                    {syntheticColumns.map((col) => (
                      <code
                        key={col}
                        className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-xs dark:bg-zinc-800"
                      >
                        {col}
                      </code>
                    ))}
                  </span>
                </>
              )}
            </span>
          </Alert>
        </div>
      )}

      <ImportSourceTabs
        selectedFile={selectedFile}
        pastedData={pastedData}
        onFileChange={onFileChange}
        onPastedDataChange={onPastedDataChange}
        onColumnsDetected={onDataColumnsChange}
        projectKind={wizardData?.projectKind}
        testIdPrefix="project-create"
        cloudPanel={
          <CloudImportPanel
            mode="select"
            initialSelection={wizardData?.cloudImport ?? null}
            onSelectionChange={(cloudImport) =>
              onWizardChange?.({ cloudImport })
            }
          />
        }
        structuredTab={
          hasStructuredTab
            ? {
                label: t('dataImport.tabs.structured', 'Klausur erfassen'),
                content: (
                  <div data-testid="wizard-structured-entry">
                    {/* eslint-disable-next-line react-hooks/static-components -- slot component resolved by useSlot */}
                    <StructuredEntry
                      data={wizardData}
                      onChange={onWizardChange}
                      variant="tab"
                    />
                  </div>
                ),
              }
            : undefined
        }
      />

      {dataColumns.length > 0 && (
        <div className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-700">
          <p className="mb-2 text-xs font-medium text-zinc-700 dark:text-zinc-300">
            {t('projects.creation.wizard.step2.detectedColumns')}
          </p>
          <div className="flex flex-wrap gap-1">
            {dataColumns.map((col) => (
              <span
                key={col}
                className="rounded bg-zinc-100 px-2 py-0.5 text-xs font-mono text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
              >
                {col}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-800/50">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          <strong>{t('projects.wizard.note')}:</strong>{' '}
          {t('projects.creation.wizard.step2.note')}
        </p>
      </div>
    </div>
  )
}
