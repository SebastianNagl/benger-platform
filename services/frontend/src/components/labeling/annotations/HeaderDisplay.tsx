/**
 * HeaderDisplay Component
 *
 * Displays header text in annotation interface
 */

import { AnnotationComponentProps } from '@/lib/labelConfig/registry'

export default function HeaderDisplay({ config }: AnnotationComponentProps) {
  const value = config.props.value || config.props.content || 'Header'
  const level = config.props.level || '3'
  const className = config.props.className || ''

  const HeadingTag = `h${level}` as keyof JSX.IntrinsicElements

  return (
    <HeadingTag
      className={`font-semibold text-zinc-900 dark:text-white ${className}`}
    >
      {value}
    </HeadingTag>
  )
}
