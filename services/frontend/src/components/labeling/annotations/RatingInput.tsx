/**
 * RatingInput Component
 *
 * Star rating input for annotations
 */

import { Label } from '@/components/shared/Label'
import { buildAnnotationResult } from '@/lib/labelConfig/dataBinding'
import { AnnotationComponentProps } from '@/lib/labelConfig/registry'
import { StarIcon } from '@heroicons/react/24/outline'
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid'
import { useState } from 'react'

export default function RatingInput({
  config,
  taskData,
  value: externalValue,
  onChange,
  onAnnotation,
}: AnnotationComponentProps) {
  const [rating, setRating] = useState<number>(externalValue || 0)
  const [hoverRating, setHoverRating] = useState<number>(0)

  // Get configuration
  const name = config.props.name || config.name || 'rating'
  const toName = config.props.toName
  const maxRating = parseInt(config.props.maxRating || '5')
  const required = config.props.required === 'true'

  // Handle rating change
  const handleRatingClick = (newRating: number) => {
    const finalRating = rating === newRating ? 0 : newRating
    setRating(finalRating)
    onChange(finalRating)

    // Create annotation result
    if (toName) {
      const result = buildAnnotationResult(name, 'Rating', finalRating, toName)
      onAnnotation(result)
    }
  }

  return (
    <div className="rating-input">
      <Label>
        {config.props.label || name}
        {required && <span className="ml-1 text-red-500">*</span>}
      </Label>

      <div className="mt-2 flex gap-1">
        {Array.from({ length: maxRating }, (_, i) => i + 1).map((star) => {
          const isActive = star <= (hoverRating || rating)
          const Icon = isActive ? StarIconSolid : StarIcon

          return (
            <button
              key={star}
              type="button"
              onClick={() => handleRatingClick(star)}
              onMouseEnter={() => setHoverRating(star)}
              onMouseLeave={() => setHoverRating(0)}
              className="p-1 transition-colors hover:text-amber-500"
            >
              <Icon
                className={`h-6 w-6 ${isActive ? 'text-amber-500' : 'text-zinc-400'}`}
              />
            </button>
          )
        })}
      </div>

      {config.props.hint && (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
          {config.props.hint}
        </p>
      )}
    </div>
  )
}
