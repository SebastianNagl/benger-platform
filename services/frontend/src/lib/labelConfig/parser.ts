/**
 * Label Configuration Parser
 *
 * Parses Label Studio XML configuration into a component tree
 * that can be rendered dynamically.
 */

export interface ParsedComponent {
  type: string
  name?: string
  props: Record<string, any>
  children: ParsedComponent[]
}

export interface ParseError {
  message: string
  line?: number
  column?: number
}

/**
 * Parse Label Studio XML configuration
 */
export function parseLabelConfig(
  xmlString: string
): ParsedComponent | ParseError {
  try {
    // Create a DOM parser
    const parser = new DOMParser()
    const doc = parser.parseFromString(xmlString, 'text/xml')

    // Check for parsing errors
    const parserError = doc.querySelector('parsererror')
    if (parserError) {
      return {
        message: parserError.textContent || 'Invalid XML',
      }
    }

    // Get root element
    const root = doc.documentElement
    if (!root) {
      return {
        message: 'No root element found',
      }
    }

    // Parse the component tree
    return parseElement(root)
  } catch (error) {
    return {
      message: error instanceof Error ? error.message : 'Unknown parsing error',
    }
  }
}

/**
 * Parse a single DOM element into a component
 */
function parseElement(element: Element): ParsedComponent {
  const component: ParsedComponent = {
    type: element.tagName,
    props: {},
    children: [],
  }

  // Extract attributes as props
  for (const attr of Array.from(element.attributes)) {
    component.props[attr.name] = attr.value

    // Special handling for 'name' attribute
    if (attr.name === 'name') {
      component.name = attr.value
    }
  }

  // Parse children
  for (const child of Array.from(element.children)) {
    component.children.push(parseElement(child))
  }

  // If element has text content and no children, add it as value
  if (element.children.length === 0 && element.textContent) {
    const text = element.textContent.trim()
    if (text) {
      component.props.content = text
    }
  }

  return component
}

/**
 * Validate parsed configuration
 */
export function validateParsedConfig(config: ParsedComponent): {
  valid: boolean
  errors: string[]
} {
  const errors: string[] = []

  // Check for required root element
  if (config.type !== 'View') {
    errors.push('Root element must be <View>')
  }

  // Validate component structure
  validateComponent(config, errors)

  return {
    valid: errors.length === 0,
    errors,
  }
}

/**
 * Recursively validate component structure
 */
function validateComponent(
  component: ParsedComponent,
  errors: string[],
  path: string = ''
): void {
  const currentPath = path ? `${path}/${component.type}` : component.type

  // Check for required attributes based on component type
  switch (component.type) {
    case 'Text':
      if (!component.props.name) {
        errors.push(`${currentPath}: Text component requires 'name' attribute`)
      }
      if (!component.props.value) {
        errors.push(`${currentPath}: Text component requires 'value' attribute`)
      }
      break

    case 'TextArea':
      if (!component.props.name) {
        errors.push(
          `${currentPath}: TextArea component requires 'name' attribute`
        )
      }
      if (!component.props.toName) {
        errors.push(
          `${currentPath}: TextArea component requires 'toName' attribute`
        )
      }
      break

    case 'Choices':
      if (!component.props.name) {
        errors.push(
          `${currentPath}: Choices component requires 'name' attribute`
        )
      }
      if (!component.props.toName) {
        errors.push(
          `${currentPath}: Choices component requires 'toName' attribute`
        )
      }
      if (component.children.length === 0) {
        errors.push(
          `${currentPath}: Choices component requires at least one Choice`
        )
      }
      break

    case 'Choice':
      if (!component.props.value) {
        errors.push(
          `${currentPath}: Choice component requires 'value' attribute`
        )
      }
      break

  }

  // Validate children
  component.children.forEach((child, index) => {
    validateComponent(child, errors, `${currentPath}[${index}]`)
  })
}

/**
 * Extract data field references from configuration
 */
export function extractDataFields(config: ParsedComponent): string[] {
  const fields = new Set<string>()

  function extractFromComponent(component: ParsedComponent) {
    // Check for $ references in props
    Object.values(component.props).forEach((value) => {
      if (typeof value === 'string' && value.startsWith('$')) {
        fields.add(value.substring(1))
      }
    })

    // Recursively check children
    component.children.forEach(extractFromComponent)
  }

  extractFromComponent(config)
  return Array.from(fields)
}

/**
 * Extract only required data field references from configuration
 * Only components marked with required="true" will have their data fields considered required
 */
export function extractRequiredDataFields(config: ParsedComponent): string[] {
  const fields = new Set<string>()

  function extractFromComponent(component: ParsedComponent) {
    // Only check required components
    if (
      component.props.required === 'true' ||
      component.props.required === true
    ) {
      // Check for $ references in props
      Object.values(component.props).forEach((value) => {
        if (typeof value === 'string' && value.startsWith('$')) {
          fields.add(value.substring(1))
        }
      })
    }

    // Recursively check children
    component.children.forEach(extractFromComponent)
  }

  extractFromComponent(config)
  return Array.from(fields)
}
