/**
 * Presentational metadata card for the project detail page.
 *
 * Renders the read-only "Project Details" block (status, created-by,
 * project id, created/updated timestamps, organizations). Extracted from
 * the ProjectDetailPage god component as a behavior-preserving sub-component;
 * the rendered DOM/text/classNames are identical to the inline version.
 */

'use client'

import type { Project } from '@/types/labelStudio'

interface ProjectMetadataCardProps {
  project: Project
  t: (key: string, params?: any) => string
}

export function ProjectMetadataCard({ project, t }: ProjectMetadataCardProps) {
  return (
    <div className="mb-8 rounded-lg bg-white p-6 shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
      <h2 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-white">
        {t('project.details.title')}
      </h2>

      <dl className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
        <div>
          <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
            {t('project.details.status')}
          </dt>
          <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
            <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800 ring-1 ring-inset ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-400 dark:ring-emerald-400/30">
              {t('project.details.active')}
            </span>
          </dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
            {t('project.details.createdBy')}
          </dt>
          <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
            {project.created_by_name ||
              t('project.details.unknown')}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
            {t('project.details.projectId')}
          </dt>
          <dd className="mt-1 font-mono text-sm text-zinc-900 dark:text-white">
            {project.id}
          </dd>
        </div>
        <div>
          <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
            {t('project.details.created')}
          </dt>
          <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
            {new Date(project.created_at).toLocaleDateString()}{' '}
            {t('project.details.at')}{' '}
            {new Date(project.created_at).toLocaleTimeString()}
          </dd>
        </div>
        {project.updated_at && (
          <div>
            <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
              {t('project.details.lastUpdated')}
            </dt>
            <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
              {new Date(project.updated_at).toLocaleDateString()}{' '}
              {t('project.details.at')}{' '}
              {new Date(project.updated_at).toLocaleTimeString()}
            </dd>
          </div>
        )}
        <div>
          <dt className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
            {t('project.details.organizations')}
          </dt>
          <dd className="mt-1 text-sm text-zinc-900 dark:text-white">
            <div className="flex items-center justify-between">
              <div className="flex flex-wrap gap-2">
                {project.organizations &&
                project.organizations.length > 0 ? (
                  project.organizations.map((org) => (
                    <span
                      key={org.id}
                      className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-400"
                    >
                      {org.name}
                    </span>
                  ))
                ) : (
                  <span className="text-zinc-500 dark:text-zinc-400">
                    {t('project.details.noOrganizations')}
                  </span>
                )}
              </div>
            </div>
          </dd>
        </div>
      </dl>
    </div>
  )
}
