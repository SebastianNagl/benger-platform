/**
 * Field Extractor for Label Studio XML Configuration
 *
 * Extracts output field names (annotation results) and input field names
 * (data references via $syntax) from a label_config XML string.
 */

import { ParsedComponent, parseLabelConfig } from './parser'

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
 */
export function extractFieldsFromLabelConfig(
  xmlString: string
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

  function walk(node: ParsedComponent) {
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
    if (typeof value === 'string' && value.startsWith('$')) {
      inputFieldSet.add(value.substring(1))
    }

    for (const child of node.children) {
      walk(child)
    }
  }

  walk(component)
  result.inputFields = Array.from(inputFieldSet)

  return result
}
