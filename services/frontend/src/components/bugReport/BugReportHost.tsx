'use client'

/**
 * The app-wide problem report dialog and its recorder. Mounted once in the
 * providers, next to the page, so the dialog also opens from the error page
 * that replaces a crashed page. While the `bug_reports` flag is on it
 * records the last errors, failed API requests and page changes
 * (lib/bugReport/recorder.ts); with the flag off it renders nothing and
 * records nothing.
 */

import { useParams, usePathname } from 'next/navigation'
import { useEffect } from 'react'

import { useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import {
  installBugReportRecorder,
  recordNavigation,
} from '@/lib/bugReport/recorder'
import { closeBugReport, useBugReportDialog } from '@/lib/bugReport/store'
import { useFeatureFlag } from '@/lib/featureFlags'
import { BUG_REPORTS } from '@/lib/featureFlags/platformFlags'

import { BugReportDialog } from './BugReportDialog'

export function BugReportHost() {
  const enabled = useFeatureFlag(BUG_REPORTS)
  if (!enabled) return null
  return <EnabledBugReportHost />
}

function EnabledBugReportHost() {
  const pathname = usePathname()
  const params = useParams()
  const uiMode = useResolvedUiMode()
  const { open, source } = useBugReportDialog()

  useEffect(() => installBugReportRecorder(), [])
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
