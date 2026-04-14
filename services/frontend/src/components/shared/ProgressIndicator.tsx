/**
 * Progress Indicator Component
 *
 * Provides visual feedback for long-running operations like:
 * - Data import/export
 * - LLM generation
 * - Bulk operations
 * - File uploads
 */

'use client'

import { CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

interface ProgressIndicatorProps {
  progress: number // 0-100
  label?: string
  sublabel?: string
  status?: 'idle' | 'running' | 'success' | 'error'
  size?: 'sm' | 'md' | 'lg'
  showPercentage?: boolean
  indeterminate?: boolean
  className?: string
}

export function ProgressIndicator({
  progress,
  label,
  sublabel,
  status = 'running',
  size = 'md',
  showPercentage = true,
  indeterminate = false,
  className = '',
}: ProgressIndicatorProps) {
  const [animatedProgress, setAnimatedProgress] = useState(0)

  useEffect(() => {
    if (!indeterminate) {
      // Animate progress changes
      const timer = setTimeout(() => {
        setAnimatedProgress(Math.max(0, Math.min(100, progress)))
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [progress, indeterminate])

  const getHeightClass = () => {
    switch (size) {
      case 'sm':
        return 'h-1'
      case 'lg':
        return 'h-3'
      default:
        return 'h-2'
    }
  }

  const getTextSizeClass = () => {
    switch (size) {
      case 'sm':
        return 'text-xs'
      case 'lg':
        return 'text-base'
      default:
        return 'text-sm'
    }
  }

  const getStatusColor = () => {
    switch (status) {
      case 'success':
        return 'bg-green-500'
      case 'error':
        return 'bg-red-500'
      case 'idle':
        return 'bg-zinc-400'
      default:
        return 'bg-emerald-500'
    }
  }

  return (
    <div className={`space-y-2 ${className}`}>
      {(label || sublabel || showPercentage) && (
        <div className="flex items-center justify-between">
          <div>
            {label && (
              <p
                className={`font-medium text-zinc-900 dark:text-white ${getTextSizeClass()}`}
              >
                {label}
              </p>
            )}
            {sublabel && (
              <p
                className={`text-zinc-500 dark:text-zinc-400 ${size === 'sm' ? 'text-xs' : 'text-sm'}`}
              >
                {sublabel}
              </p>
            )}
          </div>
          {showPercentage && !indeterminate && (
            <div className="flex items-center gap-2">
              <span
                className={`font-medium text-zinc-900 dark:text-white ${getTextSizeClass()}`}
              >
                {Math.round(animatedProgress)}%
              </span>
              {status === 'success' && (
                <CheckCircleIcon className="h-5 w-5 text-green-500" />
              )}
              {status === 'error' && (
                <XCircleIcon className="h-5 w-5 text-red-500" />
              )}
            </div>
          )}
        </div>
      )}

      <div
        className={`w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700 ${getHeightClass()}`}
      >
        {indeterminate ? (
          <div
            className={`${getHeightClass()} ${getStatusColor()} animate-indeterminate rounded-full`}
          />
        ) : (
          <div
            className={`${getHeightClass()} ${getStatusColor()} rounded-full transition-all duration-500 ease-out`}
            style={{ width: `${animatedProgress}%` }}
          />
        )}
      </div>
    </div>
  )
}

// Add CSS for indeterminate animation
const style = `
@keyframes indeterminate {
  0% {
    transform: translateX(-100%);
    width: 30%;
  }
  50% {
    width: 60%;
  }
  100% {
    transform: translateX(300%);
    width: 30%;
  }
}

.animate-indeterminate {
  animation: indeterminate 2s ease-in-out infinite;
}
`

if (typeof document !== 'undefined') {
  const styleElement = document.createElement('style')
  styleElement.textContent = style
  document.head.appendChild(styleElement)
}
