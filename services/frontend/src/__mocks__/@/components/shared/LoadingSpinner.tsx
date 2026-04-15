/**
 * Mock implementation of LoadingSpinner component
 * Issue #360: Fix frontend test mock issues
 */

interface LoadingSpinnerProps {
  size?: 'small' | 'medium' | 'large'
  className?: string
}

export function LoadingSpinner({
  size = 'medium',
  className = '',
}: LoadingSpinnerProps) {
  return (
    <div
      data-testid="loading-spinner"
      className={`loading-spinner-${size} ${className}`}
      role="status"
      aria-label="Loading"
    >
      Loading...
    </div>
  )
}

// Mock skeleton components
export const TaskDataSkeleton = ({ rows = 5 }: { rows?: number }) => (
  <div data-testid="task-data-skeleton">Loading task data ({rows} rows)...</div>
)

export const PaginationSkeleton = () => (
  <div data-testid="pagination-skeleton">Loading pagination...</div>
)

export const FilterSkeleton = () => (
  <div data-testid="filter-skeleton">Loading filters...</div>
)

export default LoadingSpinner
