/**
 * Required answer fields of a label config.
 *
 * `required="true"` on a control (Rating, Likert, Choices, Number,
 * TextArea, ...) marks a question that must be answered. On an object tag
 * (`<Text value="$x" required="true"/>`) it marks a required task data field
 * instead, which `extractRequiredDataFields` checks; those are skipped here.
 * The server applies the same rule to questionnaire responses
 * (`services/label_config/questionnaire.py`).
 */

import type { AnnotationResult } from './dataBinding'
import type { ParsedComponent } from './parser'
import { getComponent } from './registry'

export interface RequiredControl {
  name: string
  type: string
  /** What the annotator sees: the `label`, else the name. */
  label: string
}

export function extractRequiredControls(
  config: ParsedComponent,
): RequiredControl[] {
  const controls: RequiredControl[] = []
  const visit = (node: ParsedComponent) => {
    const name = node.props.name
    if (
      name &&
      String(node.props.required).toLowerCase() === 'true' &&
      getComponent(node.type)?.category === 'control'
    ) {
      controls.push({ name, type: node.type, label: node.props.label || name })
    }
    node.children.forEach(visit)
  }
  visit(config)
  return controls
}

function hasContent(value: unknown): boolean {
  if (value === null || value === undefined) return false
  if (typeof value === 'string') return value.trim().length > 0
  if (Array.isArray(value)) return value.some(hasContent)
  if (typeof value === 'object') return Object.values(value).some(hasContent)
  if (typeof value === 'number') return !Number.isNaN(value)
  return true
}

function isAnswered(control: RequiredControl, result: AnnotationResult) {
  const value = result.value
  // A star rating is cleared by clicking the chosen star again, which
  // leaves 0: ratings start at 1, so 0 is no answer.
  if (control.type === 'Rating') {
    const rating =
      value && typeof value === 'object' ? (value as any).rating : value
    return typeof rating === 'number' && rating > 0
  }
  return hasContent(value)
}

/** The required controls that `results` leave unanswered. */
export function missingRequiredControls(
  config: ParsedComponent,
  results: AnnotationResult[],
): RequiredControl[] {
  const byName = new Map(results.map((r) => [r.from_name, r]))
  return extractRequiredControls(config).filter((control) => {
    const result = byName.get(control.name)
    return !result || !isAnswered(control, result)
  })
}
