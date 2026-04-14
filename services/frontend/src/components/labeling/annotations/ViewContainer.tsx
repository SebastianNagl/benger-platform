/**
 * ViewContainer Component
 *
 * Container component for layout and styling
 */

import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import React from 'react'

interface ViewContainerProps extends AnnotationComponentProps {
  children?: React.ReactNode
}

export default function ViewContainer({
  config,
  children,
}: ViewContainerProps) {
  // Parse style from string or object
  const styleString = config.props.style || ''
  const style =
    typeof styleString === 'string'
      ? parseStyleString(styleString)
      : styleString

  // Get other properties
  const className = config.props.className || ''
  const hidden = config.props.hidden === 'true'

  if (hidden) {
    return null
  }

  return (
    <div className={`view-container ${className}`} style={style}>
      {children}
    </div>
  )
}

/**
 * Parse CSS style string to React style object
 */
function parseStyleString(styleString: string): React.CSSProperties {
  const style: React.CSSProperties = {}

  if (!styleString) return style

  // Split by semicolon and parse each property
  const declarations = styleString.split(';').filter(Boolean)

  declarations.forEach((declaration) => {
    const [property, value] = declaration.split(':').map((s) => s.trim())
    if (property && value) {
      // Convert kebab-case to camelCase
      const camelProperty = property.replace(/-([a-z])/g, (_, letter) =>
        letter.toUpperCase()
      )

      // Handle numeric values
      if (
        ['padding', 'margin', 'width', 'height'].some((p) =>
          property.includes(p)
        ) &&
        !isNaN(Number(value))
      ) {
        ;(style as any)[camelProperty] = `${value}px`
      } else {
        ;(style as any)[camelProperty] = value
      }
    }
  })

  return style
}
