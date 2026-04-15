/**
 * Component Registry
 *
 * Maps Label Studio XML tags to React components for dynamic rendering
 */

import React from 'react'
import { AnnotationResult } from './dataBinding'
import { ParsedComponent } from './parser'

export interface AnnotationComponentProps {
  config: ParsedComponent
  taskData: Record<string, any>
  value: any
  onChange: (value: any) => void
  onAnnotation: (result: AnnotationResult) => void
  hideSubmitButton?: boolean // Hide individual submit buttons when used within larger interfaces
  onSaveToDb?: (fieldName: string, value: unknown) => Promise<void> // Trigger immediate DB save (Ctrl+S in modal)
  taskId?: string // Optional task ID for draft persistence
  readOnly?: boolean // When true, components display content but disable all editing
}

export interface AnnotationComponent {
  // Component to render
  component: React.ComponentType<AnnotationComponentProps>

  // Extract annotation value from component state
  extractValue?: (state: any) => any

  // Validate component configuration
  validate?: (config: ParsedComponent) => string[]

  // Component category
  category: 'object' | 'control' | 'visual'
}

/**
 * Component registry mapping tag names to components
 */
export const componentRegistry: Record<string, AnnotationComponent> = {
  // Object tags (display data)
  Text: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/TextDisplay')
    ),
    category: 'object',
  },

  Image: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/ImageDisplay')
    ),
    category: 'object',
  },

  // Control tags (annotation tools)
  TextArea: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/TextAreaInput')
    ),
    extractValue: (value: string) => ({ text: [value] }),
    category: 'control',
  },

  Choices: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/ChoicesInput')
    ),
    extractValue: (value: string | string[]) => ({
      choices: Array.isArray(value) ? value : [value],
    }),
    category: 'control',
  },

  Labels: {
    // SpanLabelsInput handles NER-style span annotation (Issue #964)
    // When used with toName pointing to a Text element, enables text selection + labeling
    // Otherwise falls back to simple label selection mode
    component: React.lazy(
      () => import('@/components/labeling/annotations/SpanLabelsInput')
    ),
    extractValue: (value: any) => value,
    category: 'control',
  },

  Rating: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/RatingInput')
    ),
    extractValue: (value: number) => ({ rating: value }),
    category: 'control',
  },

  Likert: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/LikertInput')
    ),
    extractValue: (value: number) => ({ likert: value }),
    category: 'control',
  },

  Number: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/NumberInput')
    ),
    extractValue: (value: number) => ({ number: value }),
    category: 'control',
  },

  // Visual tags (layout and styling)
  View: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/ViewContainer')
    ),
    category: 'visual',
  },

  Header: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/HeaderDisplay')
    ),
    category: 'visual',
  },

  Style: {
    component: React.lazy(
      () => import('@/components/labeling/annotations/StyleContainer')
    ),
    category: 'visual',
  },
}

/**
 * Get component from registry
 */
export function getComponent(tagName: string): AnnotationComponent | undefined {
  return componentRegistry[tagName]
}

/**
 * Check if tag is supported
 */
export function isTagSupported(tagName: string): boolean {
  return tagName in componentRegistry
}

/**
 * Get all supported tags by category
 */
export function getSupportedTags(
  category?: 'object' | 'control' | 'visual'
): string[] {
  return Object.entries(componentRegistry)
    .filter(([_, component]) => !category || component.category === category)
    .map(([tagName]) => tagName)
}

/**
 * Register a custom component
 */
export function registerComponent(
  tagName: string,
  component: AnnotationComponent
): void {
  if (componentRegistry[tagName]) {
    // Overriding existing component
  }
  componentRegistry[tagName] = component
}

/**
 * Create component instance from parsed config
 */
export function createComponentInstance(
  config: ParsedComponent,
  taskData: Record<string, any>,
  onChange: (value: any) => void,
  onAnnotation: (result: AnnotationResult) => void
): React.ReactElement | null {
  const component = getComponent(config.type)

  if (!component) {
    // Unknown component type
    return null
  }

  const Component = component.component

  return React.createElement(Component, {
    config,
    taskData,
    value: null, // Will be managed by parent
    onChange,
    onAnnotation,
  })
}
