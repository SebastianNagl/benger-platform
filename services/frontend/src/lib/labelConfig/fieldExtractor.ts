/**
 * Field Extractor for Label Studio XML Configuration
 *
 * Extracts output field names (annotation results) and input field names
 * (data references via $syntax) from a label_config XML string.
 */

import { ParsedComponent, parseLabelConfig } from './parser'
import { expandRepeaters, REPEATER_TAG, repeaterItems, repeaterOn } from './repeater'

export interface OutputField {
  name: string
  type: string
  toName?: string
}

export interface LabelConfigFields {
  /** Fields that produce annotation output (e.g., TextArea "answer", Choices "label") */
  outputFields: OutputField[]
  /** Data fields referenced via $syntax (e.g., "context", "question") */
  inputFields: string[]
}

/** Component types that produce annotation results */
const OUTPUT_COMPONENT_TYPES = new Set([
  'TextArea',
  'Choices',
  'Labels',
  'Rating',
  'Number',
  'Angabe',
  'Notizen',
  'Gliederung',
  'Loesung',
])

/**
 * Extract output and input field names from a label_config XML string.
 * Returns empty arrays if the XML is invalid or empty.
 *
 * A `<Repeater>` contributes the array its `on` names as an input field and
 * its controls under their indexed names (`risk_0`, `risk_1`, ...), expanded
 * to the longest array any of `tasksData` holds, as the backend expands a
 * project's config. Without task data it contributes no output fields; its
 * template names (`risk_{{idx}}`) and the bindings into its array
 * (`$cases[{{idx}}].text`) are never listed.
 */
export function extractFieldsFromLabelConfig(
  xmlString: string,
  tasksData: Record<string, any>[] = [],
): LabelConfigFields {
  const result: LabelConfigFields = {
    outputFields: [],
    inputFields: [],
  }

  if (!xmlString?.trim()) return result

  const parsed = parseLabelConfig(xmlString)

  // parseLabelConfig returns a ParseError (with message) on failure
  if ('message' in parsed && !('type' in parsed)) return result

  const component = parsed as ParsedComponent
  const inputFieldSet = new Set<string>()

  function longestTask(repeater: ParsedComponent): Record<string, any> {
    let longest: Record<string, any> = {}
    let count = 0
    for (const taskData of tasksData) {
      const items = repeaterItems(repeater, taskData)
      if (items.length > count) {
        count = items.length
        longest = taskData
      }
    }
    return longest
  }

  function walk(node: ParsedComponent, collectInputs: boolean) {
    if (node.type === REPEATER_TAG) {
      const on = repeaterOn(node)
      if (collectInputs && on?.startsWith('$') && on.length > 1) {
        inputFieldSet.add(on.substring(1))
      }
      walk(expandRepeaters(node, longestTask(node)), false)
      return
    }

    // Extract output fields (components that produce annotations)
    if (OUTPUT_COMPONENT_TYPES.has(node.type) && node.name) {
      result.outputFields.push({
        name: node.name,
        type: node.type,
        toName: node.props.toName || node.props.toname,
      })
    }

    // Extract input fields (data references via $syntax)
    const value = node.props.value || node.props.Value
    if (collectInputs && typeof value === 'string' && value.startsWith('$')) {
      inputFieldSet.add(value.substring(1))
    }

    for (const child of node.children) {
      walk(child, collectInputs)
    }
  }

  walk(component, true)
  result.inputFields = Array.from(inputFieldSet)

  return result
}
