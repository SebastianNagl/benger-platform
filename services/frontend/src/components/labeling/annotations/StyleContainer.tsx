/**
 * StyleContainer Component
 *
 * Container that applies custom styles
 */

import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import React from 'react'

export default function StyleContainer({
  config,
  children,
}: AnnotationComponentProps & { children?: React.ReactNode }) {
  // For now, just pass through children
  // In future, this could apply CSS styles from config
  return <>{children}</>
}
