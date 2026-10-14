/**
 * Extension point: presence reporter of an open writing page.
 *
 * The server draft sync (`useServerDraftSync`) ticks every 30 s while a task
 * is open for writing. When the text did not change it saves nothing; an
 * extension can register a reporter that is called on those ticks, on mount
 * and when the tab is hidden or shown, with whether the tab is in the
 * foreground. The community edition registers none, so nothing is sent.
 *
 * A reporter must never throw into the writing page; failures are swallowed
 * by the caller anyway.
 *
 * There is one reporter; the last registration wins and a different owner
 * replacing it logs a warning (see ./owner.ts).
 */

import { type RegistrationOwners, recordRegistration } from './owner'

export type WritingPresenceReporter = (
  projectId: string,
  taskId: string,
  visible: boolean,
) => void | Promise<void>

let reporter: WritingPresenceReporter | null = null
const owners: RegistrationOwners = new Map()

export function registerWritingPresenceReporter(
  fn: WritingPresenceReporter | null,
) {
  recordRegistration(owners, 'writing presence reporter', 'default')
  reporter = fn
}

export function getWritingPresenceReporter(): WritingPresenceReporter | null {
  return reporter
}
