/**
 * Report API client
 *
 * Provides functions to interact with the report publishing system:
 * - Get project reports (draft or published)
 * - Update report content (superadmin only)
 * - Publish/unpublish reports and switch their visibility
 * - Recompute the report snapshot
 * - List published reports (public + org-filtered; works anonymously)
 * - Get complete report data (report + snapshot)
 */

import type { ReportChartsConfig, ReportSnapshot } from '@/types/report'
import { apiClient } from './client'

// Types matching backend schema
export interface ReportSection {
  status: 'pending' | 'completed'
  editable: boolean
  visible: boolean
}

export interface ProjectInfoSection extends ReportSection {
  title: string
  description: string
  custom_title?: string | null
  custom_description?: string | null
}

export interface DataSection extends ReportSection {
  task_count?: number
  custom_text?: string | null
  show_count: boolean
}

export interface AnnotationsSection extends ReportSection {
  annotation_count?: number
  participants?: Array<{
    id: string
    name: string
    count: number
  }>
  custom_text?: string | null
  show_count: boolean
  show_participants: boolean
  acknowledgment_text?: string | null
}

export interface GenerationSection extends ReportSection {
  models?: string[]
  custom_text?: string | null
  show_models: boolean
  show_config: boolean
}

export interface EvaluationSection extends ReportSection {
  methods?: string[]
  metrics?: Record<string, any>
  charts_config?: ReportChartsConfig
  custom_interpretation?: string | null
  conclusions?: string | null
}

export interface ReportContent {
  sections: {
    project_info: ProjectInfoSection
    data: DataSection
    annotations: AnnotationsSection
    generation: GenerationSection
    evaluation: EvaluationSection
  }
  metadata: {
    last_auto_update: string
    sections_completed: string[]
    can_publish: boolean
  }
  /** Server-computed aggregate the viewer renders. Null until refreshed. */
  snapshot?: ReportSnapshot | null
}

export interface ReportResponse {
  id: string
  project_id: string
  project_title: string
  content: ReportContent
  is_published: boolean
  /** Readable without a session (only meaningful while published). */
  is_public: boolean
  published_at?: string | null
  published_by?: string | null
  created_by: string
  created_at: string
  updated_at?: string | null
  can_publish: boolean
  can_publish_reason: string
}

export type ReportVisibility = 'public' | 'organizations'

export interface PublishedReportListItem {
  id: string
  project_id: string
  project_title: string
  published_at: string
  task_count: number
  annotation_count: number
  model_count: number
  is_public: boolean
  visibility: ReportVisibility
  organizations: Array<{
    id: string
    name: string
  }>
}

export interface MetricMetadata {
  higher_is_better: boolean
  range: [number, number]
  name: string
  category: string
}

export interface ReportDataResponse {
  report: ReportResponse
  /** The stored snapshot (null when the report was never refreshed). */
  snapshot: ReportSnapshot | null
  /** @deprecated Legacy live-aggregation fields (pre-snapshot viewer). */
  statistics?: {
    task_count: number
    annotation_count: number
    participant_count: number
    model_count: number
  }
  /** @deprecated */
  participants?: Array<{
    id: string
    username: string
    annotation_count: number
  }>
  /** @deprecated */
  models?: string[]
  /** @deprecated */
  evaluation_charts?: {
    by_model: Record<string, Record<string, number>>
    by_method: Record<string, Record<string, number>>
    metric_metadata?: Record<string, MetricMetadata>
  }
}

export interface PublishReportOptions {
  /** Publish for everyone (no login) instead of project organizations only. */
  is_public?: boolean
}

export interface ReportVisibilityOptions {
  is_public: boolean
}

/** The list endpoint is cached by the GET cache; drop it after any publication change. */
function invalidateReportLists() {
  apiClient.invalidateCache?.('/reports')
}

/**
 * Get report for a project
 * - Superadmins can view draft or published reports (incl. content.snapshot)
 * - Org members can view only published reports
 */
export async function getProjectReport(
  projectId: string
): Promise<ReportResponse> {
  return await apiClient.get(`/projects/${projectId}/report`)
}

/**
 * Update report content (superadmin only)
 * Allows editing report sections while preserving auto-populated data
 */
export async function updateProjectReport(
  projectId: string,
  content: ReportContent
): Promise<ReportResponse> {
  return await apiClient.post(`/projects/${projectId}/report`, { content })
}

/**
 * Publish a report (superadmin only)
 * Validates that all requirements are met before publishing.
 * Pass `{ is_public: true }` to make it readable without a session.
 */
export async function publishReport(
  projectId: string,
  options?: PublishReportOptions
): Promise<ReportResponse> {
  const result = await apiClient.put(
    `/projects/${projectId}/report/publish`,
    options?.is_public !== undefined
      ? { is_public: options.is_public }
      : undefined
  )
  invalidateReportLists()
  return result
}

/**
 * Unpublish a report (superadmin only)
 */
export async function unpublishReport(
  projectId: string
): Promise<ReportResponse> {
  const result = await apiClient.put(`/projects/${projectId}/report/unpublish`)
  invalidateReportLists()
  return result
}

/**
 * Switch a published report between "project organizations only" and
 * "public" (superadmin only; the API rejects it for drafts).
 */
export async function setReportVisibility(
  projectId: string,
  options: ReportVisibilityOptions
): Promise<ReportResponse> {
  const result = await apiClient.put(
    `/projects/${projectId}/report/visibility`,
    { is_public: options.is_public }
  )
  invalidateReportLists()
  return result
}

/**
 * Recompute the report snapshot from live project data (superadmin only).
 * Returns the report with the fresh `content.snapshot`.
 */
export async function refreshReport(
  projectId: string
): Promise<ReportResponse> {
  return await apiClient.post(`/projects/${projectId}/report/refresh`)
}

/**
 * List published reports
 * - Anonymous: public reports only
 * - Signed in: public reports + published reports of own organizations
 * - Superadmins: all published reports
 */
export async function listPublishedReports(): Promise<
  PublishedReportListItem[]
> {
  return await apiClient.get('/reports')
}

/**
 * Get complete report data (report + snapshot)
 * Public reports work anonymously; org reports need membership; drafts are
 * readable by superadmins.
 */
export async function getReportData(
  reportId: string
): Promise<ReportDataResponse> {
  return await apiClient.get(`/reports/${reportId}/data`)
}
