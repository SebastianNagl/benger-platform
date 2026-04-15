import React from 'react'

interface LoadingSpinnerProps {
  size?: 'small' | 'medium' | 'large'
  className?: string
}

export function LoadingSpinner({
  size = 'medium',
  className = '',
}: LoadingSpinnerProps) {
  const sizeClasses = {
    small: 'h-4 w-4',
    medium: 'h-8 w-8',
    large: 'h-12 w-12',
  }

  return (
    <div
      className={`animate-spin rounded-full border-2 border-gray-300 border-t-blue-600 ${sizeClasses[size]} ${className}`}
    />
  )
}

// Skeleton components for performance optimization (Issue #151)
interface TaskDataSkeletonProps {
  rows?: number
}

export const TaskDataSkeleton: React.FC<TaskDataSkeletonProps> = ({
  rows = 5,
}) => {
  return (
    <div className="space-y-4">
      {/* Header skeleton */}
      <div className="grid grid-cols-6 gap-4 border-b p-4">
        <div className="h-4 animate-pulse rounded bg-gray-200" />
        <div className="h-4 animate-pulse rounded bg-gray-200" />
        <div className="h-4 animate-pulse rounded bg-gray-200" />
        <div className="h-4 animate-pulse rounded bg-gray-200" />
        <div className="h-4 animate-pulse rounded bg-gray-200" />
        <div className="h-4 animate-pulse rounded bg-gray-200" />
      </div>

      {/* Row skeletons */}
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="grid grid-cols-6 gap-4 border-b p-4">
          <div className="h-6 animate-pulse rounded bg-gray-200" />
          <div className="h-6 animate-pulse rounded bg-gray-200" />
          <div className="h-6 animate-pulse rounded bg-gray-200" />
          <div className="h-6 animate-pulse rounded bg-gray-200" />
          <div className="h-6 animate-pulse rounded bg-gray-200" />
          <div className="h-6 animate-pulse rounded bg-gray-200" />
        </div>
      ))}
    </div>
  )
}

interface PageLoadingProps {
  message?: string
}

export const PageLoading: React.FC<PageLoadingProps> = ({
  message = 'Loading...',
}) => {
  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center space-y-4">
      <LoadingSpinner size="large" />
      <p className="text-gray-600">{message}</p>
    </div>
  )
}
