/**
 * Dynamic field component that renders based on field configuration
 * Issue #220: Support flexible data display without hardcoded field names
 */

import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { useI18n } from '@/contexts/I18nContext'
import { cn } from '@/lib/utils'
import { formatValue } from '@/lib/utils/fieldPath'
import React from 'react'

export interface FieldConfig {
  name: string
  label?: string
  type?:
    | 'text'
    | 'number'
    | 'boolean'
    | 'date'
    | 'list'
    | 'object'
    | 'json'
    | 'badge'
    | 'code'
  path?: string // JSONPath or dot notation path to data
  className?: string
  format?: (value: any) => string
  render?: (value: any) => React.ReactNode
}

interface DynamicFieldProps {
  field: FieldConfig
  value: any
  className?: string
}

export function DynamicField({ field, value, className }: DynamicFieldProps) {
  const { t } = useI18n()
  // Use custom render function if provided
  if (field.render) {
    return <>{field.render(value)}</>
  }

  // Format value if custom formatter provided
  const displayValue = field.format ? field.format(value) : formatValue(value)

  // Render based on field type
  switch (field.type) {
    case 'badge':
      return (
        <div className={cn('flex items-center gap-2', className)}>
          {field.label && (
            <span className="text-muted-foreground text-sm">
              {field.label}:
            </span>
          )}
          <Badge variant="outline" className={field.className}>
            {displayValue}
          </Badge>
        </div>
      )

    case 'code':
      return (
        <div className={cn('space-y-1', className)}>
          {field.label && <p className="text-sm font-medium">{field.label}</p>}
          <pre className="bg-muted overflow-x-auto rounded-md p-3 text-sm">
            <code>{displayValue}</code>
          </pre>
        </div>
      )

    case 'boolean':
      return (
        <div className={cn('flex items-center gap-2', className)}>
          {field.label && (
            <span className="text-muted-foreground text-sm">
              {field.label}:
            </span>
          )}
          <Badge variant={value ? 'default' : 'secondary'}>
            {value ? t('fields.yes') : t('fields.no')}
          </Badge>
        </div>
      )

    case 'list':
      if (!Array.isArray(value)) return null
      return (
        <div className={cn('space-y-1', className)}>
          {field.label && <p className="text-sm font-medium">{field.label}</p>}
          <ul className="list-inside list-disc space-y-1">
            {value.map((item, index) => (
              <li key={index} className="text-sm">
                {formatValue(item)}
              </li>
            ))}
          </ul>
        </div>
      )

    case 'object':
    case 'json':
      return (
        <div className={cn('space-y-1', className)}>
          {field.label && <p className="text-sm font-medium">{field.label}</p>}
          <Card className="p-3">
            <pre className="overflow-x-auto text-sm">
              {JSON.stringify(value, null, 2)}
            </pre>
          </Card>
        </div>
      )

    case 'text':
    case 'number':
    case 'date':
    default:
      // Handle long text
      const isLongText =
        typeof displayValue === 'string' && displayValue.length > 200

      if (isLongText) {
        return (
          <div className={cn('space-y-1', className)}>
            {field.label && (
              <p className="text-sm font-medium">{field.label}</p>
            )}
            <p className="text-muted-foreground whitespace-pre-wrap text-sm">
              {displayValue}
            </p>
          </div>
        )
      }

      // Inline display for short values
      return (
        <div className={cn('flex items-baseline gap-2', className)}>
          {field.label && (
            <span className="text-muted-foreground text-sm font-medium">
              {field.label}:
            </span>
          )}
          <span className="text-sm">{displayValue}</span>
        </div>
      )
  }
}

/**
 * Dynamic field group component for rendering multiple fields
 */
interface DynamicFieldGroupProps {
  fields: FieldConfig[]
  data: any
  className?: string
  title?: string
}

export function DynamicFieldGroup({
  fields,
  data,
  className,
  title,
}: DynamicFieldGroupProps) {
  return (
    <div className={cn('space-y-3', className)}>
      {title && <h3 className="text-lg font-semibold">{title}</h3>}
      {fields.map((field) => {
        const value = field.path
          ? getValueByPath(data, field.path)
          : data[field.name]

        if (value === undefined || value === null) return null

        return <DynamicField key={field.name} field={field} value={value} />
      })}
    </div>
  )
}

// Helper to get value by path (imported from utils)
function getValueByPath(data: any, path: string): any {
  if (!data || !path) return undefined

  const segments = path.split('.')
  let current = data

  for (const segment of segments) {
    if (current === null || current === undefined) {
      return undefined
    }
    current = current[segment]
  }

  return current
}
