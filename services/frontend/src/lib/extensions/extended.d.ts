// Ambient declarations for the overlay packages that src/lib/extensions/
// index.ts imports. next.config.js aliases each specifier to the overlay
// tree or to community-stub.ts, so only the registerAll() contract is typed
// here; the overlays' own exports are consumed inside the overlay trees.
declare module '@benger/extended' {
  export function registerAll(): void
}

declare module '@benger/compliance' {
  export function registerAll(): void
}
