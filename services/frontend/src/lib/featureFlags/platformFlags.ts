/**
 * The platform's own feature flags (core 2.75; registered in
 * services/shared/feature_flags/registry.py, documented in
 * docs/features/feature-flags.md). Off by default: with a flag off its
 * pages answer as not found and its entry points, panels and counts are
 * not rendered, so the platform looks as it did before the feature.
 */

/**
 * Variant experiments and their analyses: variant designs, per-item
 * answers, generation fidelity (request record, answer-format options,
 * format retry, runs cap 100), panel models, analysis runs, codes and
 * coding validation, annotator agreement and the report's Analyses section.
 */
export const VARIANT_EXPERIMENTS = 'variant_experiments'

/** The compliance records and the /compliance route shells. */
export const COMPLIANCE_RECORDS = 'compliance_records'

/**
 * The report as the project's paper: authorship of project owners and
 * organization admins, the publish rule for every project type and the
 * data, generation, human evaluation and reproducibility parts.
 */
export const REPORT_PAPER = 'report_paper'

/**
 * In-app problem reports: the "Report a problem" entries (account menu,
 * footer, error pages), the report dialog with its technical context and the
 * superadmin list at /admin/bug-reports.
 */
export const BUG_REPORTS = 'bug_reports'
