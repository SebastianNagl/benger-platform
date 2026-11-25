/**
 * Colour helpers shared by every surface that paints a label chip or a
 * highlight in a user-chosen colour.
 */

const BLACK = '#000000'
const WHITE = '#ffffff'

/**
 * Black or white text, whichever reads better on the given hex background
 * (`#rgb`, `#rrggbb` or `#rrggbbaa`, with or without the `#`; the alpha
 * channel is ignored). Anything that is not a hex colour gets black text,
 * the safe choice on the light backgrounds labels default to.
 */
export function getContrastColor(bgColor: string): string {
  let hex = (bgColor || '').trim().replace(/^#/, '')
  if (/^[0-9a-f]{3}$/i.test(hex)) {
    hex = hex
      .split('')
      .map((c) => c + c)
      .join('')
  }
  if (!/^[0-9a-f]{6}([0-9a-f]{2})?$/i.test(hex)) return BLACK

  const r = parseInt(hex.slice(0, 2), 16)
  const g = parseInt(hex.slice(2, 4), 16)
  const b = parseInt(hex.slice(4, 6), 16)
  // Perceived brightness (ITU-R BT.601 weights).
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

  return luminance > 0.5 ? BLACK : WHITE
}
