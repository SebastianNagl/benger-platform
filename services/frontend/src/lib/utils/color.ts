/**
 * Colour helpers shared by every surface that paints a label chip or a
 * highlight in a user-chosen colour.
 */

const BLACK = '#000000'
const WHITE = '#ffffff'

type Rgb = [number, number, number]

function parseHex(color: string): Rgb | null {
  let hex = color.replace(/^#/, '')
  if (/^[0-9a-f]{3}$/i.test(hex)) {
    hex = hex
      .split('')
      .map((c) => c + c)
      .join('')
  }
  if (!/^[0-9a-f]{6}([0-9a-f]{2})?$/i.test(hex)) return null
  return [
    parseInt(hex.slice(0, 2), 16),
    parseInt(hex.slice(2, 4), 16),
    parseInt(hex.slice(4, 6), 16),
  ]
}

const resolvedColors = new Map<string, Rgb | null>()
let probe: HTMLElement | null = null

/** Any other CSS colour (a name, `rgb()`, `hsl()`, ...), as the browser reads it. */
function parseCssColor(color: string): Rgb | null {
  if (typeof document === 'undefined' || !document.body) return null
  if (resolvedColors.has(color)) return resolvedColors.get(color) ?? null

  if (!probe || !probe.isConnected) {
    probe = document.createElement('span')
    probe.style.display = 'none'
    document.body.appendChild(probe)
  }
  probe.style.color = ''
  probe.style.color = color
  const match = probe.style.color
    ? /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/.exec(
        getComputedStyle(probe).color,
      )
    : null
  const rgb: Rgb | null = match
    ? [Number(match[1]), Number(match[2]), Number(match[3])]
    : null
  resolvedColors.set(color, rgb)
  return rgb
}

/**
 * Black or white text, whichever reads better on the given background. Hex
 * colours (`#rgb`, `#rrggbb` or `#rrggbbaa`, with or without the `#`) are
 * read directly, any other CSS colour through the browser; the alpha channel
 * is ignored. A background that is not a colour gets white text.
 */
export function getContrastColor(bgColor: string): string {
  const color = (bgColor || '').trim()
  if (!color) return WHITE
  const rgb = parseHex(color) ?? parseCssColor(color)
  if (!rgb) return WHITE

  const [r, g, b] = rgb
  // Perceived brightness (ITU-R BT.601 weights).
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

  return luminance > 0.5 ? BLACK : WHITE
}
