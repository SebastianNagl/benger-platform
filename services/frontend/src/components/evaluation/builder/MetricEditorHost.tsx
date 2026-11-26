/**
 * MetricEditorHost — renders a registered per-metric editor and tells its
 * caller which patches the editor wrote while mounting.
 *
 * An editor may fill in defaults through onChange as soon as it mounts.
 * Those patches are not the user's edits, so the dialog folds them into the
 * draft it compares against and an untouched edit still closes without the
 * discard prompt. React runs a parent's effects after its children's, so
 * every onChange before this component's own mount effect comes from the
 * editor's first render and its mount effects.
 */

'use client'

import type { MetricEditorProps } from '@/lib/extensions/metricEditors'
import { type ComponentType, useEffect, useRef } from 'react'

export interface MetricEditorHostProps extends Omit<
  MetricEditorProps,
  'onChange'
> {
  editor: ComponentType<MetricEditorProps>
  onChange: (patch: Record<string, unknown>, fromMount: boolean) => void
}

export function MetricEditorHost({
  editor: Editor,
  onChange,
  ...props
}: MetricEditorHostProps) {
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  return (
    <Editor
      {...props}
      onChange={(patch) => onChange(patch, !mounted.current)}
    />
  )
}
