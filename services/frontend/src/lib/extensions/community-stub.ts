/**
 * Build-time stand-in for `@benger/extended` in the community edition.
 *
 * `src/lib/extensions/index.ts` dynamically imports `@benger/extended`; the
 * call is gated on NEXT_PUBLIC_BENGER_EDITION=extended, but Turbopack still
 * has to resolve the specifier at build time. next.config.js aliases it here
 * when the extended tree is absent, so the community build never fails on a
 * missing package and `registerAll` is a no-op if it were ever reached.
 */
export function registerAll(): void {}
