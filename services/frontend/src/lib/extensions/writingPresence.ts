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
 * Each owner keeps one registration (null = no reporter); the newest one
 * whose owner is active counts (see ./active.ts), and a different owner
 * registering one logs a warning (see ./owner.ts).
 */

import { isOwnerActive } from './active'
import {
  type RegistrationOwners,
  type RegistrationStacks,
  pushRegistration,
  recordRegistration,
  resolveRegistration,
} from './owner'

export type WritingPresenceReporter = (
  projectId: string,
  taskId: string,
  visible: boolean,
) => void | Promise<void>

const KEY = 'default'
const reporters: RegistrationStacks<WritingPresenceReporter | null> = new Map()
const owners: RegistrationOwners = new Map()

export function registerWritingPresenceReporter(
  fn: WritingPresenceReporter | null,
) {
  recordRegistration(owners, 'writing presence reporter', KEY)
  pushRegistration(reporters, KEY, fn)
}

export function getWritingPresenceReporter(): WritingPresenceReporter | null {
  return resolveRegistration(reporters, KEY, isOwnerActive) ?? null
}
