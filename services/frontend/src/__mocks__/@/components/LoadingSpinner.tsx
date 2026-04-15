/**
 * Mock implementation of LoadingSpinner component (alternate import path)
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

export default LoadingSpinner
