/**
 * Simple Tooltip component using HTML title attribute
 * Can be enhanced with a proper tooltip library later
 */

import { ReactNode } from 'react'

interface TooltipProps {
  content: ReactNode | string
  children: ReactNode
  className?: string
}

export function Tooltip({ content, children, className = '' }: TooltipProps) {
  // For now, we'll use the title attribute for simple text tooltips
  // This can be enhanced later with a proper tooltip library like @radix-ui/react-tooltip

  if (typeof content === 'string') {
    return (
      <div className={className} title={content}>
        {children}
      </div>
    )
  }

  // For complex content, we'll just render without tooltip for now
  // This should be replaced with a proper tooltip implementation
  return <div className={className}>{children}</div>
}
