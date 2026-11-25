/**
 * Component Registry
 *
 * Maps Label Studio XML tags to React components for dynamic rendering
 */

import {
  type RegistrationOwners,
  recordRegistration,
} from '@/lib/extensions/owner'
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

  /**
   * Starts loading the component's code (see preloadableLazy). The form
   * preloads every component of its config and shows itself once they are
   * in, instead of building up field by field.
   */
  preload?: () => Promise<unknown>

  /** Whether the component's code is loaded (see preloadableLazy). */
  isLoaded?: () => boolean

  // Extract annotation value from component state
  extractValue?: (state: any) => any

  // Validate component configuration
  validate?: (config: ParsedComponent) => string[]

  // Component category
  category: 'object' | 'control' | 'visual'
}

/**
 * A lazily loaded annotation component that can be preloaded. Rendered
 * before its code is in, it suspends like React.lazy; rendered after
 * `preload()` settled, it renders the loaded component directly, without a
 * Suspense fallback frame. Which of the two a mounted instance uses is fixed
 * at mount, so it never remounts (and loses its state) when the code
 * arrives.
 */
export function preloadableLazy(
  loader: () => Promise<{
    default: React.ComponentType<AnnotationComponentProps>
  }>,
): Pick<AnnotationComponent, 'component' | 'preload' | 'isLoaded'> {
  let loaded: React.ComponentType<AnnotationComponentProps> | null = null
  let pending: Promise<{
    default: React.ComponentType<AnnotationComponentProps>
  }> | null = null
  const load = () => {
    pending ??= loader().then(
      (module) => {
        loaded = module.default
        return module
      },
      (error) => {
        // A failed load may be retried by the next render or preload.
        pending = null
        throw error
      },
    )
    return pending
  }
  const Lazy = React.lazy(load)
  function PreloadableComponent(props: AnnotationComponentProps) {
    const [Impl] = React.useState<
      React.ComponentType<AnnotationComponentProps>
    >(() => loaded ?? Lazy)
    return React.createElement(Impl, props)
  }
  return {
    component: PreloadableComponent,
    preload: load,
    isLoaded: () => loaded !== null,
  }
}

/**
 * Component registry mapping tag names to components
 */
export const componentRegistry: Record<string, AnnotationComponent> = {
  // Object tags (display data)
  Text: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/TextDisplay'),
    ),
    category: 'object',
  },

  Image: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/ImageDisplay'),
    ),
    category: 'object',
  },

  // Control tags (annotation tools)
  TextArea: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/TextAreaInput'),
    ),
    extractValue: (value: string) => ({ text: [value] }),
    category: 'control',
  },

  Choices: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/ChoicesInput'),
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
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/SpanLabelsInput'),
    ),
    extractValue: (value: any) => value,
    category: 'control',
  },

  Rating: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/RatingInput'),
    ),
    extractValue: (value: number) => ({ rating: value }),
    category: 'control',
  },

  Likert: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/LikertInput'),
    ),
    extractValue: (value: number) => ({ likert: value }),
    category: 'control',
  },

  Number: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/NumberInput'),
    ),
    extractValue: (value: number) => ({ number: value }),
    category: 'control',
  },

  // Visual tags (layout and styling)
  View: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/ViewContainer'),
    ),
    category: 'visual',
  },

  Header: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/HeaderDisplay'),
    ),
    category: 'visual',
  },

  Style: {
    ...preloadableLazy(
      () => import('@/components/labeling/annotations/StyleContainer'),
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
  category?: 'object' | 'control' | 'visual',
): string[] {
  return Object.entries(componentRegistry)
    .filter(([_, component]) => !category || component.category === category)
    .map(([tagName]) => tagName)
}

const componentOwners: RegistrationOwners = new Map()

/**
 * Register a custom component. Overriding an existing tag is allowed; the
 * last registration wins and a different owner replacing an earlier
 * registration logs a warning (see lib/extensions/owner.ts).
 */
export function registerComponent(
  tagName: string,
  component: AnnotationComponent,
): void {
  recordRegistration(componentOwners, 'annotation component', tagName)
  componentRegistry[tagName] = component
}

/**
 * Create component instance from parsed config
 */
export function createComponentInstance(
  config: ParsedComponent,
  taskData: Record<string, any>,
  onChange: (value: any) => void,
  onAnnotation: (result: AnnotationResult) => void,
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
