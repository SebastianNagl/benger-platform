/**
 * Which extension overlays this build enables.
 *
 * `NEXT_PUBLIC_BENGER_EXTENSIONS` is a comma separated list of overlay names
 * in load order, for example `extended,compliance`. Names are trimmed, empty
 * segments and repeats are dropped, and unknown names are ignored with one
 * console warning. When the variable is unset or blank the legacy
 * `NEXT_PUBLIC_BENGER_EDITION=extended` still enables the extended overlay
 * alone, so builds that predate the list keep working. A blank value counts
 * as unset because the Dockerfile's ENV line yields an empty string when the
 * build arg is not passed.
 *
 * Both variables carry the NEXT_PUBLIC_ prefix, so Next inlines them at build
 * time and the list is fixed per build. next.config.js derives the Turbopack
 * aliases and transpilePackages from the same rule (parseEnabledExtensions
 * there) and must stay in sync with this module. The env is read on every
 * call rather than cached: tests flip the variables between cases.
 */

export const EXTENSION_NAMES = ['extended', 'compliance'] as const

export type ExtensionName = (typeof EXTENSION_NAMES)[number]

function isExtensionName(name: string): name is ExtensionName {
  return (EXTENSION_NAMES as readonly string[]).includes(name)
}

let warnedFor: string | null = null

/** Enabled overlay names in load order. */
export function enabledExtensions(): ExtensionName[] {
  const raw = process.env.NEXT_PUBLIC_BENGER_EXTENSIONS
  if (raw === undefined || raw.trim() === '') {
    return process.env.NEXT_PUBLIC_BENGER_EDITION === 'extended'
      ? ['extended']
      : []
  }
  const enabled: ExtensionName[] = []
  const unknown: string[] = []
  for (const part of raw.split(',')) {
    const name = part.trim()
    if (name === '') continue
    if (!isExtensionName(name)) {
      unknown.push(name)
      continue
    }
    if (!enabled.includes(name)) enabled.push(name)
  }
  if (unknown.length > 0 && warnedFor !== raw) {
    warnedFor = raw
    console.warn(
      `[extensions] unknown extension(s) ignored in NEXT_PUBLIC_BENGER_EXTENSIONS: ${unknown.join(', ')}`,
    )
  }
  return enabled
}

/** Whether the named overlay is enabled in this build. */
export function isExtensionEnabled(name: string): boolean {
  return (enabledExtensions() as string[]).includes(name)
}

/** Test helper: forget which value already produced an unknown-name warning. */
export function _resetEnabledExtensionsForTests(): void {
  warnedFor = null
}
