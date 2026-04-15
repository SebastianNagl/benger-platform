/**
 * TextDisplay Component
 *
 * Displays text data from task fields using Label Studio's $ syntax
 */

import { useI18n } from '@/contexts/I18nContext'
import { resolveDataBinding } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'

export default function TextDisplay({
  config,
  taskData,
}: AnnotationComponentProps) {
  const { t } = useI18n()
  // Get the value to display
  const valueExpression = config.props.value
  const value = resolveDataBinding(valueExpression, taskData)

  // Get display properties
  const name = config.props.name || config.name
  const showLabel = config.props.showLabel !== 'false'
  const className = config.props.className || ''
  const style = config.props.style || {}

  // Handle missing data
  if (value === undefined || value === null) {
    return (
      <div className="italic text-zinc-500 dark:text-zinc-400">
        {t('labeling.display.noData', { field: valueExpression })}
      </div>
    )
  }

  return (
    <div className={`text-display ${className}`} style={style}>
      {showLabel && name && (
        <label className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {name}
        </label>
      )}
      <div className="prose prose-sm max-w-none dark:prose-invert">
        {typeof value === 'object' ? (
          <pre className="overflow-x-auto rounded-md bg-zinc-100 p-3 dark:bg-zinc-800">
            {JSON.stringify(value, null, 2)}
          </pre>
        ) : (
          <p className="whitespace-pre-wrap">{String(value)}</p>
        )}
      </div>
    </div>
  )
}
