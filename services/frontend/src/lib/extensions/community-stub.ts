/**
 * Build-time stand-in for a disabled overlay (`@benger/extended`,
 * `@benger/compliance`).
 *
 * `src/lib/extensions/index.ts` dynamically imports every overlay with a
 * static specifier; the loader only calls the enabled ones, but Turbopack
 * still has to resolve each specifier at build time. next.config.js aliases
 * disabled overlays (and enabled ones whose tree is absent) here, so a build
 * never fails on a missing package and `registerAll` is a no-op if it were
 * ever reached.
 */
export function registerAll(): void {}
