/**
 * ImageDisplay Component
 *
 * Displays images for annotation
 */

import { resolveDataBinding } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'

export default function ImageDisplay({
  config,
  taskData,
}: AnnotationComponentProps) {
  const valueExpression = config.props.value
  const imageSrc = resolveDataBinding(valueExpression, taskData)
  const name = config.props.name || config.name
  const width = config.props.width
  const height = config.props.height

  if (!imageSrc) {
    return (
      <div className="italic text-zinc-500 dark:text-zinc-400">
        No image data for field: {valueExpression}
      </div>
    )
  }

  return (
    <div className="image-display">
      {name && (
        <label className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {name}
        </label>
      )}
      {/* eslint-disable-next-line @next/next/no-img-element -- Dynamic data-bound image URL */}
      <img
        src={imageSrc}
        alt={name || 'Annotation image'}
        width={width}
        height={height}
        className="h-auto max-w-full rounded-lg border border-zinc-200 dark:border-zinc-700"
      />
    </div>
  )
}
