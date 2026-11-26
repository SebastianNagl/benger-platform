'use client'

/**
 * The app-wide problem report dialog and its recorder. Mounted once in the
 * providers, next to the page, so the dialog also opens from the error page
 * that replaces a crashed page. It records the last errors, failed API
 * requests and page changes (lib/bugReport/recorder.ts) from the moment the
 * app loads, because the flag only answers after auth and the failures of
 * the first page load are often what a report is about. Once the
 * `bug_reports` flag reads off it renders nothing, stops recording and
 * drops what it had.
 */

import { useParams, usePathname } from 'next/navigation'
import { useEffect } from 'react'

import { useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import {
  installBugReportRecorder,
  recordNavigation,
  stopBugReportRecorder,
} from '@/lib/bugReport/recorder'
import { closeBugReport, useBugReportDialog } from '@/lib/bugReport/store'
import { useFeatureFlagStatus } from '@/lib/featureFlags'
import { BUG_REPORTS } from '@/lib/featureFlags/platformFlags'

import { BugReportDialog } from './BugReportDialog'

// Before any component effect runs: the page's first requests start in
// effects, while the flag is still loading.
installBugReportRecorder()

export function BugReportHost() {
  const status = useFeatureFlagStatus(BUG_REPORTS)
  useEffect(() => {
    if (status === 'off') stopBugReportRecorder()
    else if (status === 'on') installBugReportRecorder()
  }, [status])
  if (status !== 'on') return null
  return <EnabledBugReportHost />
}

function EnabledBugReportHost() {
  const pathname = usePathname()
  const params = useParams()
  const uiMode = useResolvedUiMode()
  const { open, source } = useBugReportDialog()

  useEffect(() => {
    if (pathname) recordNavigation(pathname)
  }, [pathname])

  return (
    <BugReportDialog
      open={open}
      onClose={closeBugReport}
      source={source}
      extraContext={{
        routeParams: (params ?? undefined) as
          Record<string, string | string[]> | undefined,
        uiMode,
      }}
    />
  )
}

export default BugReportHost
