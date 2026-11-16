/**
 * jsdom has no PointerEvent, so `fireEvent.pointerEnter(el, { pointerType })`
 * would drop the pointer type. Tests that tell mouse from touch install this
 * minimal stand-in first.
 */
export function installPointerEventPolyfill() {
  if (typeof window === 'undefined' || window.PointerEvent) return
  class PointerEventPolyfill extends MouseEvent {
    pointerType: string
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params)
      this.pointerType = params.pointerType ?? ''
    }
  }
  window.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent
}
