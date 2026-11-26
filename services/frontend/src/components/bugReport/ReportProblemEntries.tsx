'use client'

/**
 * The entry points of "Report a problem", each rendered only while the
 * `bug_reports` flag is on for the viewer:
 *
 * - ReportProblemMenuEntry: a row of the account menu (AuthButton), plus
 *   "Problem reports" (/admin/bug-reports) for superadmins.
 * - ReportProblemFooterLink: a link-styled button in the footer's small print.
 * - ReportProblemButton: a button for the error pages.
 *
 * All of them open the dialog BugReportHost renders.
 */

import {
  ExclamationTriangleIcon,
  InboxStackIcon,
} from '@heroicons/react/24/outline'
import Link from 'next/link'

import { Button } from '@/components/shared/Button'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { openBugReport, type BugReportSource } from '@/lib/bugReport/store'
import { useFeatureFlag } from '@/lib/featureFlags'
import { BUG_REPORTS } from '@/lib/featureFlags/platformFlags'

const MENU_ROW =
  'flex w-full items-center px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-700'

interface MenuEntryProps {
  /** Called when an entry is used so the host can close its dropdown. */
  onNavigate?: () => void
}

export function ReportProblemMenuEntry(props: MenuEntryProps) {
  const enabled = useFeatureFlag(BUG_REPORTS)
  if (!enabled) return null
  return <EnabledMenuEntry {...props} />
}

function EnabledMenuEntry({ onNavigate }: MenuEntryProps) {
  const { t } = useI18n()
  const { user } = useAuth()
  return (
    <>
      <button
        type="button"
        className={MENU_ROW}
        data-testid="auth-menu-report-problem"
        onClick={() => {
          onNavigate?.()
          openBugReport('menu')
        }}
      >
        <ExclamationTriangleIcon className="mr-3 h-4 w-4" />
        {t('bugReport.entry')}
      </button>
      {user?.is_superadmin && (
        <Link
          href="/admin/bug-reports"
          className={MENU_ROW}
          data-testid="auth-menu-bug-reports"
          onClick={onNavigate}
        >
          <InboxStackIcon className="mr-3 h-4 w-4" />
          {t('bugReport.admin.menu')}
        </Link>
      )}
    </>
  )
}

export function ReportProblemFooterLink() {
  const { t } = useI18n()
  const enabled = useFeatureFlag(BUG_REPORTS)
  if (!enabled) return null
  return (
    <button
      type="button"
      onClick={() => openBugReport('footer')}
      data-testid="footer-report-problem"
      className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-300"
    >
      {t('bugReport.entry')}
    </button>
  )
}

export function ReportProblemButton({
  source = 'error-page',
  onClick,
}: {
  source?: BugReportSource
  /** Replaces opening the shared dialog (the crash card has its own). */
  onClick?: () => void
}) {
  const { t } = useI18n()
  const enabled = useFeatureFlag(BUG_REPORTS)
  if (!enabled) return null
  return (
    <Button
      type="button"
      variant="outline"
      data-testid="error-report-problem"
      onClick={onClick ?? (() => openBugReport(source))}
    >
      {t('bugReport.entry')}
    </Button>
  )
}
