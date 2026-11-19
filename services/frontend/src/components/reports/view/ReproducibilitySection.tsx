import { formatCount, formatDate, formatDateTime } from '@/lib/reports/format'
import type { ReportReproducibility } from '@/types/report'
import clsx from 'clsx'
import type { ReactNode } from 'react'
import type { TranslateFn } from './chartTheme'
import {
  FactList,
  HashValue,
  JsonDetails,
  MISSING,
  NUM,
  RecordTable,
  TD,
  TH,
} from './records'
import { Prose, ReportSection, SubHeading } from './ReportSection'

function Block({
  title,
  children,
  testId,
}: {
  title: string
  children: ReactNode
  testId?: string
}) {
  return (
    <div className="mt-6 break-inside-avoid-page" data-testid={testId}>
      <SubHeading>{title}</SubHeading>
      {children}
    </div>
  )
}

/** The appendix of versions and hashes a reader needs to reproduce the numbers. */
export function ReproducibilitySection({
  repro,
  generatedAt,
  note,
  locale,
  t,
}: {
  repro: ReportReproducibility
  generatedAt?: string | null
  /** The author's own notes on reproducing the study. */
  note?: string | null
  locale: string
  t: TranslateFn
}) {
  const copy = t('reports.view.records.copyHash')
  const hash = (value: string | null | undefined) => (
    <HashValue value={value} label={copy} />
  )
  return (
    <ReportSection
      title={t('reports.view.records.reproducibility')}
      id="reproducibility"
    >
      {note && (
        <div className="mb-6">
          <Prose>{note}</Prose>
        </div>
      )}
      <FactList
        items={[
          {
            label: t('reports.view.records.snapshotHash'),
            value: hash(repro.snapshot_sha256),
            testId: 'repro-snapshot-hash',
          },
          {
            label: t('reports.view.records.snapshotTime'),
            value: formatDateTime(generatedAt, locale) || MISSING,
          },
          {
            label: t('reports.view.records.platformVersion'),
            value: (
              <span className="font-mono text-xs break-all">
                {repro.platform.app_version
                  ? t('reports.view.records.platformVersionValue', {
                      app: repro.platform.app_version,
                      core: repro.platform.core_api_version,
                    })
                  : t('reports.view.records.platformVersionCoreOnly', {
                      core: repro.platform.core_api_version,
                    })}
              </span>
            ),
          },
          {
            label: t('reports.view.records.labelConfig'),
            value: repro.label_config.sha256 ? (
              <div className="space-y-1">
                {repro.label_config.version && (
                  <div>
                    {t('reports.view.records.version', {
                      version: repro.label_config.version,
                    })}
                  </div>
                )}
                {hash(repro.label_config.sha256)}
              </div>
            ) : (
              MISSING
            ),
          },
        ]}
      />
      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
        {t('reports.view.records.snapshotHashHint')}
      </p>

      {repro.models.length > 0 && (
        <Block title={t('reports.view.records.modelIds')} testId="repro-models">
          <ul className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            {repro.models.map((m) => (
              <li key={m.id} className="min-w-0">
                <code className="font-mono text-xs break-all">{m.id}</code>
                {m.provider && (
                  <span className="text-xs whitespace-nowrap text-zinc-500 dark:text-zinc-400">
                    {' '}
                    ({m.provider})
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Block>
      )}

      {repro.prompt_structures.length > 0 && (
        <Block
          title={t('reports.view.records.promptStructures')}
          testId="repro-structures"
        >
          <RecordTable
            head={
              <>
                <th scope="col" className={TH}>
                  {t('reports.view.records.structure')}
                </th>
                <th scope="col" className={clsx(TH, NUM)}>
                  {t('reports.view.records.generations')}
                </th>
                <th scope="col" className={TH}>
                  {t('reports.view.records.definitionHash')}
                </th>
              </>
            }
          >
            {repro.prompt_structures.map((s) => (
              <tr key={s.key ?? ''}>
                <td className={clsx(TD, s.key != null && 'font-mono text-xs')}>
                  {s.key ?? t('reports.view.records.noStructure')}
                </td>
                <td className={clsx(TD, NUM)}>
                  {formatCount(s.generations, locale)}
                </td>
                <td className={clsx(TD, 'min-w-48')}>
                  {hash(s.definition_sha256)}
                </td>
              </tr>
            ))}
          </RecordTable>
        </Block>
      )}

      {repro.evaluation_configs.length > 0 && (
        <Block
          title={t('reports.view.records.evaluationConfigs')}
          testId="repro-eval-configs"
        >
          <RecordTable
            head={
              <>
                <th scope="col" className={TH}>
                  {t('reports.view.records.configuration')}
                </th>
                <th scope="col" className={TH}>
                  {t('reports.view.judge')}
                </th>
                <th scope="col" className={clsx(TH, NUM)}>
                  n
                </th>
                <th scope="col" className={TH}>
                  {t('reports.view.records.parametersHash')}
                </th>
              </>
            }
          >
            {repro.evaluation_configs.flatMap((c) => {
              const runs = c.judge_runs.length > 0 ? c.judge_runs : [null]
              return runs.map((run, i) => (
                <tr key={`${c.id}-${i}`}>
                  {i === 0 && (
                    <td className={clsx(TD, 'align-top')} rowSpan={runs.length}>
                      <div className="font-medium text-zinc-900 dark:text-white">
                        {c.name || c.metric}
                      </div>
                      <div className="font-mono text-xs break-all text-zinc-500 dark:text-zinc-400">
                        {c.metric}
                        {c.id ? ` · ${c.id}` : ''}
                      </div>
                    </td>
                  )}
                  <td
                    className={clsx(
                      TD,
                      'align-top font-mono text-xs break-all',
                    )}
                  >
                    {run?.judge_model ?? MISSING}
                  </td>
                  <td className={clsx(TD, NUM, 'align-top')}>
                    {run ? formatCount(run.samples, locale) : MISSING}
                  </td>
                  <td className={clsx(TD, 'min-w-48 align-top')}>
                    {run ? hash(run.parameters_sha256) : MISSING}
                    {run?.parameters != null && (
                      <JsonDetails
                        summary={t('reports.view.records.showParameters')}
                        value={run.parameters}
                      />
                    )}
                  </td>
                </tr>
              ))
            })}
          </RecordTable>
        </Block>
      )}

      {repro.variant_designs.length > 0 && (
        <Block
          title={t('reports.view.records.variantDesigns')}
          testId="repro-designs"
        >
          <RecordTable
            head={
              <>
                <th scope="col" className={TH}>
                  {t('reports.view.records.design')}
                </th>
                <th scope="col" className={TH}>
                  {t('reports.view.records.contentHash')}
                </th>
                <th scope="col" className={TH}>
                  {t('reports.view.records.specHash')}
                </th>
              </>
            }
          >
            {repro.variant_designs.map((d) => (
              <tr key={d.key}>
                <td className={clsx(TD, 'align-top')}>
                  <div className="font-mono text-xs">{d.key}</div>
                  <div className="text-xs text-zinc-500 dark:text-zinc-400">
                    {t('reports.view.records.version', { version: d.version })}
                    {' · '}
                    {d.status === 'frozen'
                      ? t('reports.view.records.designFrozenShort')
                      : t('reports.view.records.designDraft')}
                  </div>
                </td>
                <td className={clsx(TD, 'min-w-48 align-top')}>
                  {d.content_hash ? (
                    hash(d.content_hash)
                  ) : (
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">
                      {t('reports.view.records.notFrozen')}
                    </span>
                  )}
                </td>
                <td className={clsx(TD, 'min-w-48 align-top')}>
                  {hash(d.spec_sha256)}
                </td>
              </tr>
            ))}
          </RecordTable>
        </Block>
      )}

      {repro.imports.length > 0 && (
        <Block title={t('reports.view.records.imports')} testId="repro-imports">
          <ul className="space-y-1 text-sm">
            {repro.imports.map((imp, i) => (
              <li
                key={`${imp.payload_sha256}-${i}`}
                className="flex flex-wrap items-baseline gap-x-3"
              >
                <span className="text-xs whitespace-nowrap text-zinc-500 dark:text-zinc-400">
                  {formatDate(imp.completed_at, locale) || MISSING}
                </span>
                {hash(imp.payload_sha256)}
                {imp.no_op && (
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {t('reports.view.records.noOpImport')}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Block>
      )}

      {repro.analysis_runs.length > 0 && (
        <Block
          title={t('reports.view.records.analysisRuns')}
          testId="repro-analysis-runs"
        >
          <div className="space-y-4">
            {repro.analysis_runs.map((run) => (
              <div
                key={run.id}
                className="break-inside-avoid rounded-md border border-zinc-200 p-4 dark:border-zinc-800"
                data-testid="repro-analysis-run"
              >
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium text-zinc-900 dark:text-white">
                    {run.name}
                  </span>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {formatDateTime(run.completed_at, locale)}
                  </span>
                </div>
                <FactList
                  items={[
                    {
                      label: t('reports.view.records.specHash'),
                      value: hash(run.spec_hash),
                    },
                    {
                      label: t('reports.view.records.frameHash'),
                      value: hash(run.frame_sha256),
                    },
                    {
                      label: t('reports.view.records.engine'),
                      value: t('reports.view.records.engineValue', {
                        engine: run.engine_version,
                        spec: run.spec_version,
                      }),
                    },
                    {
                      label: t('reports.view.records.lockfileHash'),
                      value: hash(run.lockfile_sha256),
                    },
                    {
                      label: t('reports.view.records.frameRows'),
                      value: t('reports.view.records.frameRowsValue', {
                        rows: formatCount(run.frame_rows ?? 0, locale),
                        estimates: formatCount(run.estimates_count, locale),
                      }),
                    },
                    {
                      label: t('reports.view.records.seed'),
                      value:
                        run.seed === null ? (
                          MISSING
                        ) : (
                          <code className="font-mono text-xs">{run.seed}</code>
                        ),
                    },
                    {
                      label: t('reports.view.records.libraries'),
                      value:
                        run.library_versions &&
                        Object.keys(run.library_versions).length > 0 ? (
                          <span className="font-mono text-xs break-all">
                            {Object.entries(run.library_versions)
                              .sort(([a], [b]) => a.localeCompare(b))
                              .map(([lib, version]) => `${lib} ${version}`)
                              .join(', ')}
                          </span>
                        ) : (
                          MISSING
                        ),
                    },
                  ]}
                />
              </div>
            ))}
          </div>
        </Block>
      )}
    </ReportSection>
  )
}
