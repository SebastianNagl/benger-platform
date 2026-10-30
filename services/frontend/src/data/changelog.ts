import type { ChangelogEntry } from '@/lib/extensions/changelog'

/**
 * Platform changelog entries, newest first. One short user-facing bullet
 * per new feature. The entry here carries id, date and audience; the text
 * lives at `changelogEntries.<id>` in src/locales/<locale>/changelog.json
 * (de, en and fr). Extended-edition entries live in the extended package
 * and are merged in via registerChangelogEntries().
 */
export const PLATFORM_CHANGELOG: ChangelogEntry[] = [
  {
    id: '2026-10-30-project-prompts-card',
    date: '2026-10-30',
    audience: 'benger',
  },
  {
    id: '2026-10-19-runtime-extension-switches',
    date: '2026-10-19',
    audience: 'both',
  },
  {
    id: '2026-10-14-french-language-menu',
    date: '2026-10-14',
    audience: 'both',
  },
  {
    id: '2026-10-13-evaluations-limited-model-answers',
    date: '2026-10-13',
    audience: 'benger',
  },
  {
    id: '2026-10-13-api-access-organizations-personally',
    date: '2026-10-13',
    audience: 'benger',
    requires: 'publicApi',
  },
  {
    id: '2026-10-12-belong-several-organizations-project',
    date: '2026-10-12',
    audience: 'benger',
  },
  {
    id: '2026-10-09-tasks-row-shows-result',
    date: '2026-10-09',
    audience: 'benger',
  },
  {
    id: '2026-10-09-project-settings-decide-separately',
    date: '2026-10-09',
    audience: 'benger',
  },
  { id: '2026-10-08-api-keys-set-per', date: '2026-10-08', audience: 'benger' },
  {
    id: '2026-10-08-legal-experience-profile-enter',
    date: '2026-10-08',
    audience: 'both',
  },
  {
    id: '2026-10-07-clicking-model-model-list',
    date: '2026-10-07',
    audience: 'benger',
  },
  {
    id: '2026-10-07-writing-annotations-exams-notice',
    date: '2026-10-07',
    audience: 'both',
  },
  {
    id: '2026-10-07-models-choose-claude-opus',
    date: '2026-10-07',
    audience: 'both',
  },
  {
    id: '2026-10-06-publicly-shared-projects-visitors',
    date: '2026-10-06',
    audience: 'both',
  },
  {
    id: '2026-10-06-group-organization-own-roles',
    date: '2026-10-06',
    audience: 'both',
  },
  {
    id: '2026-09-30-sign-yourself-invitation-same',
    date: '2026-09-30',
    audience: 'both',
  },
  {
    id: '2026-09-30-platform-cannot-load-keys',
    date: '2026-09-30',
    audience: 'both',
  },
  {
    id: '2026-09-26-grading-sheets-outline-such',
    date: '2026-09-26',
    audience: 'both',
  },
  {
    id: '2026-09-26-ai-grading-grading-sheet',
    date: '2026-09-26',
    audience: 'both',
  },
  {
    id: '2026-09-24-data-management-mark-complete',
    date: '2026-09-24',
    audience: 'benger',
  },
  {
    id: '2026-09-24-models-page-custom-models',
    date: '2026-09-24',
    audience: 'benger',
  },
  {
    id: '2026-09-19-sign-password-reset-recognise',
    date: '2026-09-19',
    audience: 'both',
  },
  {
    id: '2026-09-19-organizations-listed-alphabetically-organization',
    date: '2026-09-19',
    audience: 'both',
  },
  {
    id: '2026-09-17-pending-invitation-list-shows',
    date: '2026-09-17',
    audience: 'both',
  },
  {
    id: '2026-09-17-member-lists-show-roles',
    date: '2026-09-17',
    audience: 'both',
  },
  {
    id: '2026-09-17-registering-learning-platform-link',
    date: '2026-09-17',
    audience: 'both',
  },
  {
    id: '2026-09-17-projects-task-assignments-imported',
    date: '2026-09-17',
    audience: 'both',
  },
  {
    id: '2026-09-17-people-removed-organization-invited',
    date: '2026-09-17',
    audience: 'both',
  },
  {
    id: '2026-09-17-organization-admins-set-manage',
    date: '2026-09-17',
    audience: 'benger',
  },
  {
    id: '2026-09-17-contributors-admins-organization-see',
    date: '2026-09-17',
    audience: 'benger',
  },
  {
    id: '2026-09-17-guides-learning-platform-integration',
    date: '2026-09-17',
    audience: 'both',
  },
  {
    id: '2026-09-16-guides-include-data-protection',
    date: '2026-09-16',
    audience: 'both',
  },
  {
    id: '2026-09-16-models-choose-gpt-6',
    date: '2026-09-16',
    audience: 'both',
  },
  {
    id: '2026-09-15-exams-worked-stay-viewable',
    date: '2026-09-15',
    audience: 'both',
  },
  {
    id: '2026-09-15-notification-settings-entries-gradings',
    date: '2026-09-15',
    audience: 'benger',
  },
  {
    id: '2026-09-15-evaluation-run-page-opens',
    date: '2026-09-15',
    audience: 'benger',
  },
  {
    id: '2026-09-15-project-page-participation-card',
    date: '2026-09-15',
    audience: 'benger',
  },
  {
    id: '2026-09-15-local-drafts-bound-signed',
    date: '2026-09-15',
    audience: 'benger',
  },
  {
    id: '2026-09-15-evaluation-run-page-matches',
    date: '2026-09-15',
    audience: 'benger',
  },
  {
    id: '2026-09-15-project-import-keeps-project',
    date: '2026-09-15',
    audience: 'benger',
  },
  {
    id: '2026-09-15-metric-catalogue-task-position',
    date: '2026-09-15',
    audience: 'benger',
  },
  {
    id: '2026-09-15-personal-api-keys-provider',
    date: '2026-09-15',
    audience: 'benger',
  },
  {
    id: '2026-09-15-uploaded-word-files-longer',
    date: '2026-09-15',
    audience: 'both',
  },
  {
    id: '2026-09-15-cost-estimate-grading-sheet',
    date: '2026-09-15',
    audience: 'both',
  },
  {
    id: '2026-09-08-tidier-toolbar-users-organizations',
    date: '2026-09-08',
    audience: 'both',
  },
  {
    id: '2026-09-03-public-projects-hardened-public',
    date: '2026-09-03',
    audience: 'benger',
  },
  {
    id: '2026-09-02-reports-rebuilt-reports-published',
    date: '2026-09-02',
    audience: 'benger',
  },
  {
    id: '2026-09-02-architecture-page-updated-open',
    date: '2026-09-02',
    audience: 'benger',
  },
  {
    id: '2026-09-02-guides-how-guides-page',
    date: '2026-09-02',
    audience: 'benger',
  },
  {
    id: '2026-09-02-generation-placeholders-such-sachverhalt',
    date: '2026-09-02',
    audience: 'benger',
  },
  {
    id: '2026-09-02-landing-page-group-network',
    date: '2026-09-02',
    audience: 'benger',
  },
  {
    id: '2026-09-02-top-right-context-menu',
    date: '2026-09-02',
    audience: 'benger',
  },
  {
    id: '2026-09-02-leaderboards-exam-cohort-tab',
    date: '2026-09-02',
    audience: 'benger',
  },
  {
    id: '2026-09-01-organizations-split-members-projects',
    date: '2026-09-01',
    audience: 'benger',
  },
  {
    id: '2026-08-31-project-page-billing-card',
    date: '2026-08-31',
    audience: 'benger',
  },
  {
    id: '2026-08-31-cloud-storage-import-organizations',
    date: '2026-08-31',
    audience: 'benger',
  },
  {
    id: '2026-08-31-project-wizard-clearer-data',
    date: '2026-08-31',
    audience: 'benger',
  },
  {
    id: '2026-08-31-project-wizard-enter-exam',
    date: '2026-08-31',
    audience: 'benger',
  },
  {
    id: '2026-08-31-organization-management-edited-description',
    date: '2026-08-31',
    audience: 'benger',
  },
  {
    id: '2026-08-25-ai-grading-rubric-own',
    date: '2026-08-25',
    audience: 'benger',
  },
  {
    id: '2026-08-25-everyone-switch-between-student',
    date: '2026-08-25',
    audience: 'both',
  },
  {
    id: '2026-08-25-project-type-exam-flashcard',
    date: '2026-08-25',
    audience: 'benger',
  },
  {
    id: '2026-08-24-changelog-page-overview-whats',
    date: '2026-08-24',
    audience: 'both',
  },
]
