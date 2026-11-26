/**
 * Open state of the app-wide problem report dialog (BugReportHost renders
 * it). Entry points (account menu, footer, error page) call
 * `openBugReport(source)`; module state read through useSyncExternalStore,
 * so no provider is needed.
 */

import { useSyncExternalStore } from 'react'

/** Where the dialog was opened from; travels with the report. */
export type BugReportSource = 'menu' | 'footer' | 'error-page' | 'crash'

interface DialogState {
  open: boolean
  source: BugReportSource
}

let state: DialogState = { open: false, source: 'menu' }
const listeners = new Set<() => void>()

function set(next: DialogState) {
  state = next
  listeners.forEach((listener) => listener())
}

export function openBugReport(source: BugReportSource): void {
  set({ open: true, source })
}

export function closeBugReport(): void {
  set({ ...state, open: false })
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

const getSnapshot = () => state

export function useBugReportDialog(): DialogState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}

export function resetBugReportDialogForTests(): void {
  state = { open: false, source: 'menu' }
  listeners.clear()
}
