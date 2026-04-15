/**
 * ChoicesInput Component
 *
 * Radio buttons or checkboxes for choice-based annotations
 */

import { Label } from '@/components/shared/Label'
import { buildAnnotationResult } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import { useEffect, useState } from 'react'

export default function ChoicesInput({
  config,
  taskData,
  value: externalValue,
  onChange,
  onAnnotation,
}: AnnotationComponentProps) {
  const [selectedValues, setSelectedValues] = useState<string[]>(() => {
    // Initialize from external value if provided and not null
    if (externalValue !== undefined && externalValue !== null) {
      return Array.isArray(externalValue) ? externalValue : [externalValue]
    }
    // Otherwise start empty, will be filled by useEffect if there are pre-selected choices
    return []
  })

  // Get configuration
  const name = config.props.name || config.name || 'choices'
  const toName = config.props.toName
  const choice = config.props.choice || 'single' // single or multiple
  const required = config.props.required === 'true'
  const layout = config.props.layout || 'vertical' // vertical or horizontal

  // Extract choices from children
  const choices = config.children
    .filter((child) => child.type === 'Choice')
    .map((child) => ({
      value: child.props.value || child.props.content || '',
      label:
        child.props.alias || child.props.value || child.props.content || '',
      selected: child.props.selected === 'true',
    }))

  // Initialize with pre-selected choices from config (if external value not provided)
  useEffect(() => {
    if (
      (externalValue === null || externalValue === undefined) &&
      selectedValues.length === 0
    ) {
      const preSelected = choices.filter((c) => c.selected).map((c) => c.value)
      if (preSelected.length > 0) {
        setSelectedValues(preSelected)
        onChange(choice === 'single' ? preSelected[0] : preSelected)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [choices, choice]) // Run when choices change (e.g., new config)

  // Sync external value changes
  useEffect(() => {
    if (externalValue !== undefined && externalValue !== null) {
      setSelectedValues(
        Array.isArray(externalValue) ? externalValue : [externalValue]
      )
    } else if (externalValue === null) {
      setSelectedValues([])
    }
  }, [externalValue])

  // Handle selection change
  const handleChange = (value: string, checked: boolean) => {
    let newValues: string[]

    if (choice === 'single') {
      // Radio button behavior
      newValues = checked ? [value] : []
    } else {
      // Checkbox behavior
      if (checked) {
        newValues = [...selectedValues, value]
      } else {
        newValues = selectedValues.filter((v) => v !== value)
      }
    }

    setSelectedValues(newValues)
    const outputValue = choice === 'single' ? newValues[0] || null : newValues
    onChange(outputValue)

    // Create annotation result
    if (toName) {
      const result = buildAnnotationResult(name, 'Choices', outputValue, toName)
      onAnnotation(result)
    }
  }

  const inputType = choice === 'single' ? 'radio' : 'checkbox'
  const layoutClass =
    layout === 'horizontal' ? 'flex flex-wrap gap-4' : 'space-y-2'

  return (
    <div className="choices-input">
      <Label>
        {config.props.label || name}
        {required && <span className="ml-1 text-red-500">*</span>}
      </Label>

      <div className={`mt-2 ${layoutClass}`}>
        {choices.map((choiceOption) => (
          <label
            key={choiceOption.value}
            className="flex cursor-pointer items-center space-x-2 hover:text-emerald-600 dark:hover:text-emerald-400"
          >
            <input
              type={inputType}
              name={name}
              value={choiceOption.value}
              checked={selectedValues.includes(choiceOption.value)}
              onChange={(e) =>
                handleChange(choiceOption.value, e.target.checked)
              }
              className="form-radio text-emerald-600 focus:ring-emerald-500"
              required={required && selectedValues.length === 0}
            />
            <span className="text-sm">{choiceOption.label}</span>
          </label>
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
