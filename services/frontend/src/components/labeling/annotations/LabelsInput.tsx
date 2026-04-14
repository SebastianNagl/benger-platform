/**
 * LabelsInput Component
 *
 * Multi-select labels for annotation (like tags)
 */

import { Label } from '@/components/shared/Label'
import { buildAnnotationResult } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import { useState } from 'react'

export default function LabelsInput({
  config,
  taskData,
  value: externalValue,
  onChange,
  onAnnotation,
}: AnnotationComponentProps) {
  const [selectedLabels, setSelectedLabels] = useState<string[]>(
    externalValue || []
  )

  // Get configuration
  const name = config.props.name || config.name || 'labels'
  const toName = config.props.toName
  const required = config.props.required === 'true'

  // Extract labels from children
  const labels = config.children
    .filter((child) => child.type === 'Label')
    .map((child) => ({
      value: child.props.value || child.props.content || '',
      background: child.props.background || '#e5e7eb',
      selected: child.props.selected === 'true',
    }))

  // Handle label toggle
  const handleLabelToggle = (labelValue: string) => {
    const newLabels = selectedLabels.includes(labelValue)
      ? selectedLabels.filter((l) => l !== labelValue)
      : [...selectedLabels, labelValue]

    setSelectedLabels(newLabels)
    onChange(newLabels)

    // Create annotation result
    if (toName) {
      const result = buildAnnotationResult(name, 'Labels', newLabels, toName)
      onAnnotation(result)
    }
  }

  return (
    <div className="labels-input">
      <Label>
        {config.props.label || name}
        {required && <span className="ml-1 text-red-500">*</span>}
      </Label>

      <div className="mt-2 flex flex-wrap gap-2">
        {labels.map((label) => (
          <button
            key={label.value}
            type="button"
            onClick={() => handleLabelToggle(label.value)}
            className={cn(
              'rounded-full px-3 py-1 text-sm font-medium transition-colors',
              selectedLabels.includes(label.value)
                ? 'bg-emerald-600 text-white'
                : 'bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600'
            )}
            style={{
              backgroundColor: selectedLabels.includes(label.value)
                ? label.background
                : undefined,
            }}
          >
            {label.value}
          </button>
        ))}
      </div>

      {config.props.hint && (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          {config.props.hint}
        </p>
      )}
    </div>
  )
}

// Import cn utility
function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(' ')
}
