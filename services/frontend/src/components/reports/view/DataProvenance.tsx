import { formatCount, formatDate, formatNumber } from '@/lib/reports/format'
import type {
  ReportDataSection,
  ReportVariantDesign,
  ReportVariantFactor,
} from '@/types/report'
import clsx from 'clsx'
import type { TranslateFn } from './chartTheme'
import {
  HashValue,
  JsonDetails,
  MISSING,
  NUM,
  RecordTable,
  TD,
  TH,
} from './records'
import { SubHeading } from './ReportSection'

const FACTOR_ROLES = ['manipulated', 'counterbalanced', 'blocking', 'nuisance']

function formatBytes(bytes: number | null, locale: string): string {
  if (bytes === null) return MISSING
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${formatNumber(value, locale, unit === 0 ? 0 : 1)} ${units[unit]}`
}

function FactorLine({
  factor,
  t,
}: {
  factor: ReportVariantFactor
  t: TranslateFn
}) {
  const levels = factor.levels ?? []
  const more =
    factor.level_count !== null && factor.level_count > levels.length
      ? factor.level_count - levels.length
      : 0
  const role = FACTOR_ROLES.includes(factor.role)
    ? t(`reports.view.records.factorRole.${factor.role}`)
    : factor.role
  return (
    <li className="min-w-0">
      <span className="font-medium text-zinc-900 dark:text-white">
        {factor.name}
      </span>{' '}
      <span className="text-xs text-zinc-500 dark:text-zinc-400">({role})</span>
      {levels.length > 0 && (
        <span className="block text-xs break-words text-zinc-600 dark:text-zinc-300">
          {levels.map(String).join(', ')}
          {more > 0 &&
            ` ${t('reports.view.records.moreLevels', { count: more })}`}
        </span>
      )}
    </li>
  )
}

function DesignRow({
  design,
  locale,
  t,
}: {
  design: ReportVariantDesign
  locale: string
  t: TranslateFn
}) {
  const frozen = design.status === 'frozen'
  return (
    <tr data-testid="variant-design-row">
      <td className={clsx(TD, 'align-top')}>
        <div className="font-medium text-zinc-900 dark:text-white">
          {design.title || design.key}
        </div>
        {design.title && (
          <div className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
            {design.key}
          </div>
        )}
        <span
          className={clsx(
            'mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium',
            frozen
              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
              : 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300',
          )}
        >
          {frozen
            ? t('reports.view.records.designFrozen', {
                date: formatDate(design.frozen_at, locale),
              })
            : t('reports.view.records.designDraft')}
        </span>
      </td>
      <td className={clsx(TD, 'min-w-48 align-top')}>
        <ul className="space-y-1">
          {design.factors.map((f) => (
            <FactorLine key={f.name} factor={f} t={t} />
          ))}
        </ul>
        {design.unit && (
          <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {t('reports.view.records.unit', { unit: design.unit })}
          </div>
        )}
      </td>
      <td className={clsx(TD, NUM, 'align-top')}>
        {formatCount(design.unit_count, locale)}
      </td>
      <td className={clsx(TD, NUM, 'align-top')}>
        {formatCount(design.cell_count, locale)}
      </td>
      <td className={clsx(TD, NUM, 'align-top')}>
        {formatCount(design.task_count, locale)}
      </td>
    </tr>
  )
}

/** Variant designs and import provenance, inside the report's Data section. */
export function DataProvenance({
  data,
  locale,
  t,
}: {
  data: ReportDataSection | undefined
  locale: string
  t: TranslateFn
}) {
  if (!data) return null
  const { variant_designs: designs, imports } = data
  if (designs.length === 0 && imports.length === 0) return null
  return (
    <div className="mt-6 space-y-6" data-testid="data-provenance">
      {designs.length > 0 && (
        <div>
          <SubHeading>{t('reports.view.records.variantDesigns')}</SubHeading>
          <RecordTable
            testId="variant-designs"
            head={
              <>
                <th scope="col" className={TH}>
                  {t('reports.view.records.design')}
                </th>
                <th scope="col" className={TH}>
                  {t('reports.view.records.factors')}
                </th>
                <th scope="col" className={clsx(TH, NUM)}>
                  {t('reports.view.records.units')}
                </th>
                <th scope="col" className={clsx(TH, NUM)}>
                  {t('reports.view.records.cells')}
                </th>
                <th scope="col" className={clsx(TH, NUM)}>
                  {t('reports.view.tasks')}
                </th>
              </>
            }
          >
            {designs.map((d) => (
              <DesignRow key={d.key} design={d} locale={locale} t={t} />
            ))}
          </RecordTable>
        </div>
      )}

      {imports.length > 0 && (
        <div>
          <SubHeading>{t('reports.view.records.imports')}</SubHeading>
          <RecordTable
            testId="imports"
            head={
              <>
                <th scope="col" className={TH}>
                  {t('reports.view.records.importedOn')}
                </th>
                <th scope="col" className={TH}>
                  {t('reports.view.records.importMode')}
                </th>
                <th scope="col" className={clsx(TH, NUM)}>
                  {t('reports.view.tasks')}
                </th>
                <th scope="col" className={clsx(TH, NUM)}>
                  {t('reports.view.records.size')}
                </th>
                <th scope="col" className={TH}>
                  {t('reports.view.records.payloadHash')}
                </th>
              </>
            }
          >
            {imports.map((imp, i) => (
              <tr key={`${imp.payload_sha256}-${i}`} data-testid="import-row">
                <td className={clsx(TD, 'align-top whitespace-nowrap')}>
                  {formatDate(imp.completed_at, locale) || MISSING}
                  {imp.no_op && (
                    <div className="text-xs text-zinc-500 dark:text-zinc-400">
                      {t('reports.view.records.noOpImport')}
                    </div>
                  )}
                </td>
                <td className={clsx(TD, 'align-top')}>
                  {imp.mode || imp.format || MISSING}
                </td>
                <td className={clsx(TD, NUM, 'align-top')}>
                  {formatCount(imp.task_count, locale)}
                </td>
                <td className={clsx(TD, NUM, 'align-top whitespace-nowrap')}>
                  {formatBytes(imp.byte_size, locale)}
                </td>
                <td className={clsx(TD, 'min-w-48 align-top')}>
                  <HashValue
                    value={imp.payload_sha256}
                    label={t('reports.view.records.copyHash')}
                  />
                  {imp.declared_manifest &&
                    (imp.declared_manifest.truncated ? (
                      <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                        {t('reports.view.records.manifestTooLarge')}
                      </div>
                    ) : imp.declared_manifest.content === undefined ? (
                      <div className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                        <div>{t('reports.view.records.declaredManifest')}</div>
                        <HashValue
                          value={imp.declared_manifest.sha256}
                          label={t('reports.view.records.copyHash')}
                        />
                      </div>
                    ) : (
                      <JsonDetails
                        summary={t('reports.view.records.declaredManifest')}
                        value={imp.declared_manifest.content}
                      />
                    ))}
                </td>
              </tr>
            ))}
          </RecordTable>
          {data.imports_truncated && (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              {t('reports.view.records.importsTruncated', {
                shown: formatCount(imports.length, locale),
                total: formatCount(data.import_count, locale),
              })}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
