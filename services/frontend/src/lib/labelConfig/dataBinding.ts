/**
 * Data Binding System
 *
 * Handles data binding between task data and annotation components
 * using Label Studio's $ syntax.
 */

/**
 * Resolve data binding expressions
 * Handles both flat and nested data structures (e.g., taskData.data.field)
 *
 * Examples:
 * - "$text" -> taskData.text or taskData.data.text
 * - "$question.content" -> taskData.question.content or taskData.data.question.content
 * - "static text" -> "static text"
 */
export function resolveDataBinding(
  value: string | any,
  taskData: Record<string, any>
): any {
  // Only process strings that start with $
  if (typeof value !== 'string' || !value.startsWith('$')) {
    return value
  }

  // Remove $ prefix and resolve path
  const path = value.substring(1)

  // First try to find the field at the root level
  let result = getNestedValue(taskData, path)

  // If not found at root level and taskData has a 'data' property, check there
  if (
    (result === undefined || result === null) &&
    taskData.data &&
    typeof taskData.data === 'object'
  ) {
    result = getNestedValue(taskData.data, path)
  }

  return result
}

/**
 * Get nested value from object using dot notation
 */
function getNestedValue(obj: any, path: string): any {
  const parts = path.split('.')
  let current = obj

  for (const part of parts) {
    if (current == null || typeof current !== 'object') {
      return undefined
    }
    current = current[part]
  }

  return current
}

/**
 * Resolve all data bindings in props object
 */
export function resolvePropsDataBindings(
  props: Record<string, any>,
  taskData: Record<string, any>
): Record<string, any> {
  const resolved: Record<string, any> = {}

  for (const [key, value] of Object.entries(props)) {
    resolved[key] = resolveDataBinding(value, taskData)
  }

  return resolved
}

/**
 * Create annotation result from component state
 * Follows Label Studio annotation format
 */
export interface AnnotationResult {
  id?: string // Optional unique identifier for the annotation
  value: any
  from_name: string
  to_name: string
  type: string
}

/**
 * Build annotation results from component values
 */
export function buildAnnotationResult(
  componentName: string,
  componentType: string,
  value: any,
  toName: string
): AnnotationResult {
  // Map component types to annotation types
  const annotationTypeMap: Record<string, string> = {
    TextArea: 'textarea',
    Choices: 'choices',
    Labels: 'labels',
    Rating: 'rating',
    Likert: 'likert',
    Number: 'number',
    Angabe: 'angabe',
  }

  const annotationType =
    annotationTypeMap[componentType] || componentType.toLowerCase()

  // Format value based on type
  let formattedValue = value
  if (componentType === 'TextArea') {
    formattedValue = { text: [value] }
  } else if (componentType === 'Choices') {
    formattedValue = { choices: Array.isArray(value) ? value : [value] }
  }

  return {
    value: formattedValue,
    from_name: componentName,
    to_name: toName,
    type: annotationType,
  }
}

/**
 * Map old annotation format to new format
 */
export function mapLegacyAnnotation(
  fieldName: string,
  value: any
): AnnotationResult | null {
  // Map legacy field names to new format
  const legacyFieldMap: Record<string, { type: string; toName: string }> = {
    short_answer: { type: 'textarea', toName: 'question' },
    reasoning: { type: 'textarea', toName: 'question' },
    confidence: { type: 'choices', toName: 'question' },
  }

  const mapping = legacyFieldMap[fieldName]
  if (!mapping) return null

  return buildAnnotationResult(
    fieldName,
    mapping.type === 'textarea' ? 'TextArea' : 'Choices',
    value,
    mapping.toName
  )
}

/**
 * Build span annotation result for NER-style labeling
 * Follows Label Studio format for span annotations
 *
 * Issue #964: Add Span Annotation as a project type
 */
export interface SpanValue {
  id: string
  start: number
  end: number
  text: string
  labels: string[]
}

export function buildSpanAnnotationResult(
  fromName: string,
  toName: string,
  spans: SpanValue[]
): AnnotationResult {
  // Store all spans in a single annotation result
  // This matches how DynamicAnnotationInterface stores one result per from_name
  return {
    from_name: fromName,
    to_name: toName,
    type: 'labels',
    value: {
      // Array of span annotations following Label Studio format
      spans: spans.map((span) => ({
        id: span.id,
        start: span.start,
        end: span.end,
        text: span.text,
        labels: span.labels,
      })),
    },
  }
}

/**
 * Parse span annotations from annotation result
 * Converts stored format back to SpanValue array
 */
export function parseSpanAnnotations(
  result: AnnotationResult | null
): SpanValue[] {
  if (!result || !result.value) return []

  // Handle new format with spans array
  if (result.value.spans && Array.isArray(result.value.spans)) {
    return result.value.spans.map((span: any) => ({
      id:
        span.id ||
        `span-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      start: span.start || 0,
      end: span.end || 0,
      text: span.text || '',
      labels: span.labels || [],
    }))
  }

  // Handle legacy format with single span
  if (result.value.start !== undefined) {
    return [
      {
        id:
          result.id ||
          `span-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        start: result.value.start,
        end: result.value.end,
        text: result.value.text || '',
        labels: result.value.labels || [],
      },
    ]
  }

  return []
}

/**
 * Validate required fields are present in task data
 * Handles both flat and nested data structures (e.g., taskData.data.field)
 */
export function validateTaskDataFields(
  requiredFields: string[],
  taskData: Record<string, any>
): { valid: boolean; missingFields: string[] } {
  const missingFields = requiredFields.filter((field) => {
    // First try to find the field at the root level
    let value = getNestedValue(taskData, field)

    // If not found at root level and taskData has a 'data' property, check there
    if (
      (value === undefined || value === null) &&
      taskData.data &&
      typeof taskData.data === 'object'
    ) {
      value = getNestedValue(taskData.data, field)
    }

    return value === undefined || value === null
  })

  return {
    valid: missingFields.length === 0,
    missingFields,
  }
}

/**
 * Label Studio Format Conversion Functions
 *
 * Issue #964: Convert between BenGER internal format and Label Studio format
 * for span annotations during export/import.
 *
 * BenGER format (internal):
 * {
 *   "from_name": "label",
 *   "to_name": "text",
 *   "type": "labels",
 *   "value": {
 *     "spans": [
 *       {"id": "span-1", "start": 0, "end": 10, "text": "John Smith", "labels": ["PERSON"]}
 *     ]
 *   }
 * }
 *
 * Label Studio format:
 * [
 *   {
 *     "id": "span-1",
 *     "from_name": "label",
 *     "to_name": "text",
 *     "type": "labels",
 *     "value": {"start": 0, "end": 10, "text": "John Smith", "labels": ["PERSON"]}
 *   }
 * ]
 */

/**
 * Convert BenGER annotation format to Label Studio format for export.
 * Flattens span annotations: one result with spans array -> multiple results.
 */
export function convertToLabelStudioFormat(
  annotations: AnnotationResult[]
): AnnotationResult[] {
  const result: AnnotationResult[] = []

  for (const annotation of annotations) {
    // Handle span/labels type with nested spans array
    if (annotation.type === 'labels' && annotation.value?.spans) {
      // Flatten: create one result per span
      for (const span of annotation.value.spans) {
        result.push({
          id: span.id,
          from_name: annotation.from_name,
          to_name: annotation.to_name,
          type: 'labels',
          value: {
            start: span.start,
            end: span.end,
            text: span.text,
            labels: span.labels,
          },
        })
      }
    } else {
      // Non-span annotations pass through unchanged
      result.push(annotation)
    }
  }

  return result
}

/**
 * Convert Label Studio format to BenGER internal format for import.
 * Consolidates span annotations: multiple results -> one result with spans array.
 */
export function convertFromLabelStudioFormat(
  annotations: AnnotationResult[]
): AnnotationResult[] {
  const result: AnnotationResult[] = []
  const spanGroups: Map<
    string,
    { annotation: AnnotationResult; spans: SpanValue[] }
  > = new Map()

  for (const annotation of annotations) {
    // Check if this is a Label Studio span annotation (labels type with value.start)
    if (
      annotation.type === 'labels' &&
      annotation.value?.start !== undefined &&
      annotation.value?.end !== undefined
    ) {
      // Group by from_name + to_name
      const key = `${annotation.from_name}:${annotation.to_name}`

      if (!spanGroups.has(key)) {
        spanGroups.set(key, {
          annotation: {
            from_name: annotation.from_name,
            to_name: annotation.to_name,
            type: 'labels',
            value: { spans: [] },
          },
          spans: [],
        })
      }

      const group = spanGroups.get(key)!
      group.spans.push({
        id:
          annotation.id ||
          `span-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        start: annotation.value.start,
        end: annotation.value.end,
        text: annotation.value.text || '',
        labels: annotation.value.labels || [],
      })
    } else if (annotation.type === 'labels' && annotation.value?.spans) {
      // Already in BenGER format, pass through
      result.push(annotation)
    } else {
      // Non-span annotations pass through unchanged
      result.push(annotation)
    }
  }

  // Add consolidated span groups to result
  spanGroups.forEach((group) => {
    group.annotation.value = { spans: group.spans }
    result.push(group.annotation)
  })

  return result
}
