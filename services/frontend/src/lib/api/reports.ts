/**
 * Report API client
 *
 * Provides functions to interact with the report publishing system:
 * - Get project reports (draft or published)
 * - Update report content (report authors only)
 * - Publish/unpublish reports and switch their visibility
 * - Recompute the report snapshot
 * - List published reports (public + org-filtered; works anonymously)
 * - Get complete report data (report + snapshot)
 */

import type {
  ReportChartsConfig,
  ReportExhibitFilters,
  ReportExhibitType,
  ReportSnapshot,
} from '@/types/report'
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
  /** Show variant designs and import provenance (default true). */
  show_provenance?: boolean
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
  /** Show inter-annotator agreement from the snapshot (default true). */
  show_agreement?: boolean
  /** Show the validations of the codes the Analyses section's runs read
   *  (default true). */
  show_code_validations?: boolean
  acknowledgment_text?: string | null
}

export interface GenerationSection extends ReportSection {
  models?: string[]
  custom_text?: string | null
  show_models: boolean
  show_config: boolean
  /** Show the per-model generation table (default true). */
  show_details?: boolean
}

export interface EvaluationSection extends ReportSection {
  methods?: string[]
  metrics?: Record<string, any>
  charts_config?: ReportChartsConfig
  custom_interpretation?: string | null
  conclusions?: string | null
  /** Show the human evaluation results (default true). */
  show_human_evaluation?: boolean
}

/** One exhibit of an Analyses run: how it draws which estimates. */
export interface AnalysisExhibitContent {
  /** 1 to 64 letters, digits, '-' or '_', unique within the run. */
  id: string
  type: ReportExhibitType
  title?: string | null
  caption?: string | null
  filters?: ReportExhibitFilters
  /** Equivalence bound set a forest draws (default the first), null none. */
  band?: number | null
}

/** One run of the Analyses section with the author's text and exhibits. */
export interface AnalysisRunContent {
  run_id: string
  title?: string | null
  text?: string | null
  exhibits: AnalysisExhibitContent[]
}

/** The Analyses section: completed single-project runs the author picked;
 *  the snapshot copies the estimates their exhibits select. */
export interface AnalysesSection {
  visible?: boolean
  custom_text?: string | null
  runs?: AnalysisRunContent[]
}

/** An analysis run the Analyses section can show. */
export interface ReportAnalysisRunOption {
  id: string
  name: string
  spec_hash: string
  engine_version: string
  frame_rows: number | null
  estimates_count: number | null
  completed_at: string | null
  /** A private model may appear in it: only members see it, and a public
   *  report cannot show it. */
  member_only: boolean
}

/** Reproducibility appendix; visible unless the author switched it off. */
export interface ReproducibilitySection {
  visible?: boolean
  custom_text?: string | null
}

export interface ReportContent {
  sections: {
    project_info: ProjectInfoSection
    data: DataSection
    annotations: AnnotationsSection
    generation: GenerationSection
    evaluation: EvaluationSection
    analyses?: AnalysesSection
    reproducibility?: ReproducibilitySection
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
  /** The caller authors this report: the project owner, an admin of one of
   *  the project's organizations or a superadmin. */
  can_edit?: boolean
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
  /** Completed analysis runs (absent from APIs before CORE 2.67). */
  analysis_count?: number
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
 * - Report authors (project owner, org admins of the project, superadmins)
 *   can view draft or published reports (incl. content.snapshot)
 * - Org members can view only published reports
 */
export async function getProjectReport(
  projectId: string,
  options: RequestInit = {},
): Promise<ReportResponse> {
  return await apiClient.get(`/projects/${projectId}/report`, options)
}

/**
 * Update report content (report authors only)
 * Allows editing report sections while preserving auto-populated data
 */
export async function updateProjectReport(
  projectId: string,
  content: ReportContent,
): Promise<ReportResponse> {
  return await apiClient.post(`/projects/${projectId}/report`, { content })
}

/**
 * Publish a report (report authors only)
 * Validates that all requirements are met before publishing.
 * Pass `{ is_public: true }` to make it readable without a session.
 */
export async function publishReport(
  projectId: string,
  options?: PublishReportOptions,
): Promise<ReportResponse> {
  const result = await apiClient.put(
    `/projects/${projectId}/report/publish`,
    options?.is_public !== undefined
      ? { is_public: options.is_public }
      : undefined,
  )
  invalidateReportLists()
  return result
}

/**
 * Unpublish a report (report authors only)
 */
export async function unpublishReport(
  projectId: string,
): Promise<ReportResponse> {
  const result = await apiClient.put(`/projects/${projectId}/report/unpublish`)
  invalidateReportLists()
  return result
}

/**
 * Switch a published report between "project organizations only" and
 * "public" (report authors only; the API rejects it for drafts).
 */
export async function setReportVisibility(
  projectId: string,
  options: ReportVisibilityOptions,
): Promise<ReportResponse> {
  const result = await apiClient.put(
    `/projects/${projectId}/report/visibility`,
    { is_public: options.is_public },
  )
  invalidateReportLists()
  return result
}

/**
 * Recompute the report snapshot from live project data (report authors only).
 * Returns the report with the fresh `content.snapshot`.
 */
export async function refreshReport(
  projectId: string,
): Promise<ReportResponse> {
  return await apiClient.post(`/projects/${projectId}/report/refresh`)
}

/**
 * The analysis runs the report's Analyses section can show (report authors
 * only): completed runs of the project that read no other project, newest
 * first.
 */
export async function listReportAnalysisRuns(
  projectId: string,
): Promise<ReportAnalysisRunOption[]> {
  const page = (await apiClient.get(
    `/projects/${projectId}/report/analysis-runs`,
    { cache: 'no-store' },
  )) as { items?: ReportAnalysisRunOption[] }
  return page?.items ?? []
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
 * readable by report authors.
 */
export async function getReportData(
  reportId: string,
): Promise<ReportDataResponse> {
  return await apiClient.get(`/reports/${reportId}/data`)
}
