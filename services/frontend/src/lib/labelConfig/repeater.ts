/**
 * Label Studio <Repeater> expansion for the labeling UI.
 *
 * `<Repeater on="$cases" indexFlag="{{idx}}">` repeats its children once per
 * element of the task-data array `on` names. Label Studio expands it while
 * parsing the config against a task (`web/libs/editor/src/core/Tree.tsx`):
 * the index flag is replaced by the 0-based element index in every attribute
 * of every repeated element, and the Repeater becomes a View holding one View
 * per element. This module does the same on BenGER's parsed component tree,
 * so annotations are stored under the same indexed names (`risk_0`,
 * `risk_1`, ...) Label Studio and the backend
 * (`services/shared/label_config_repeater.py`) use.
 *
 * Text content is not substituted (Label Studio only replaces attributes),
 * and `mode="pagination"` renders all items stacked.
 */

import { resolveDataBinding } from './dataBinding'
import type { ParsedComponent } from './parser'

export const REPEATER_TAG = 'Repeater'
export const DEFAULT_INDEX_FLAG = '{{idx}}'

/** Repeater attributes the expanded View does not keep. */
const REPEATER_PROPS = new Set([
  'on',
  'indexflag',
  'mode',
  'answerkey',
  'answerkeystart',
])

/** A Repeater prop, matched case-insensitively as Label Studio lower-cases
 * attribute names (`attrsToProps`). */
function repeaterProp(
  component: ParsedComponent,
  name: string,
): string | undefined {
  const lowered = name.toLowerCase()
  for (const [key, value] of Object.entries(component.props)) {
    if (key.toLowerCase() === lowered && typeof value === 'string') {
      return value
    }
  }
  return undefined
}

export function indexFlagOf(component: ParsedComponent): string {
  return repeaterProp(component, 'indexFlag') || DEFAULT_INDEX_FLAG
}

/** Whether the parsed tree contains a Repeater. */
export function hasRepeater(component: ParsedComponent): boolean {
  return (
    component.type === REPEATER_TAG ||
    component.children.some((child) => hasRepeater(child))
  )
}

/** The array a Repeater iterates over in `taskData` (empty when the binding
 * names no array, as Label Studio then repeats nothing). */
export function repeaterItems(
  component: ParsedComponent,
  taskData: Record<string, any>,
): unknown[] {
  const on = repeaterProp(component, 'on')
  if (!on || !on.startsWith('$')) return []
  const value = resolveDataBinding(on, taskData || {})
  return Array.isArray(value) ? value : []
}

function substitute(
  component: ParsedComponent,
  indexFlag: string,
  index: number,
): ParsedComponent {
  const props: Record<string, any> = {}
  for (const [key, value] of Object.entries(component.props)) {
    // `content` is the element's text, which Label Studio leaves as it is.
    props[key] =
      key !== 'content' && typeof value === 'string'
        ? value.split(indexFlag).join(String(index))
        : value
  }
  return {
    type: component.type,
    name:
      typeof component.name === 'string'
        ? component.name.split(indexFlag).join(String(index))
        : component.name,
    props,
    children: component.children.map((child) =>
      substitute(child, indexFlag, index),
    ),
  }
}

/**
 * The parsed tree with every Repeater expanded against `taskData`. A tree
 * without a Repeater is returned as it is (same object).
 */
export function expandRepeaters(
  component: ParsedComponent,
  taskData: Record<string, any>,
): ParsedComponent {
  if (!hasRepeater(component)) return component
  if (component.type === REPEATER_TAG) {
    const indexFlag = indexFlagOf(component)
    const props: Record<string, any> = {}
    for (const [key, value] of Object.entries(component.props)) {
      if (!REPEATER_PROPS.has(key.toLowerCase())) props[key] = value
    }
    return {
      type: 'View',
      props,
      children: repeaterItems(component, taskData).map((_, index) => ({
        type: 'View',
        props: {},
        children: component.children.map((child) =>
          substitute(child, indexFlag, index),
        ),
      })),
    }
  }
  return {
    ...component,
    children: component.children.map((child) =>
      expandRepeaters(child, taskData),
    ),
  }
}
