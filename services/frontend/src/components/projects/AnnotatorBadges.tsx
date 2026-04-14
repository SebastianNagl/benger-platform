/**
 * Annotator Badges Component
 * Displays assigned users as colored badges with initials
 */

import { Tooltip } from '@/components/shared/Tooltip'
import { useI18n } from '@/contexts/I18nContext'

interface Assignment {
  id: string
  user_id: string
  user_name?: string
  user_email?: string
  status?: 'assigned' | 'in_progress' | 'completed' | 'skipped'
  priority?: number
}

interface AnnotatorBadgesProps {
  assignments: Assignment[]
  maxVisible?: number
  size?: 'xs' | 'sm' | 'md' | 'lg'
  showStatus?: boolean
  onUnassign?: (assignmentId: string) => void
  canUnassign?: boolean
  onAssign?: () => void
  canAssign?: boolean
}

// Generate consistent color based on user ID
function getUserColor(userId: string): string {
  const colors = [
    'bg-purple-200 text-purple-800 dark:bg-purple-800/30 dark:text-purple-300',
    'bg-blue-200 text-blue-800 dark:bg-blue-800/30 dark:text-blue-300',
    'bg-green-200 text-green-800 dark:bg-green-800/30 dark:text-green-300',
    'bg-pink-200 text-pink-800 dark:bg-pink-800/30 dark:text-pink-300',
    'bg-amber-200 text-amber-800 dark:bg-amber-800/30 dark:text-amber-300',
    'bg-indigo-200 text-indigo-800 dark:bg-indigo-800/30 dark:text-indigo-300',
    'bg-teal-200 text-teal-800 dark:bg-teal-800/30 dark:text-teal-300',
    'bg-orange-200 text-orange-800 dark:bg-orange-800/30 dark:text-orange-300',
  ]

  // Simple hash function to get consistent color
  let hash = 0
  for (let i = 0; i < userId.length; i++) {
    hash = (hash << 5) - hash + userId.charCodeAt(i)
    hash = hash & hash // Convert to 32bit integer
  }
  return colors[Math.abs(hash) % colors.length]
}

// Extract initials from name or email
function getInitials(name?: string, email?: string): string {
  if (name) {
    const parts = name.trim().split(/\s+/)
    if (parts.length >= 2) {
      // First letter of first name + first letter of last name
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    } else if (parts.length === 1) {
      // First two letters of single name
      return parts[0].slice(0, 2).toUpperCase()
    }
  }

  if (email) {
    // Use first two letters of email before @
    const emailName = email.split('@')[0]
    return emailName.slice(0, 2).toUpperCase()
  }

  return '??'
}

// Get status indicator
function getStatusIndicator(status?: string) {
  switch (status) {
    case 'completed':
      return (
        <div className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-white dark:bg-zinc-900">
          <div className="h-2 w-2 rounded-full bg-emerald-500" />
        </div>
      )
    case 'in_progress':
      return (
        <div className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-white dark:bg-zinc-900">
          <div className="h-2 w-2 animate-pulse rounded-full bg-yellow-500" />
        </div>
      )
    case 'skipped':
      return (
        <div className="absolute -bottom-0.5 -right-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-white dark:bg-zinc-900">
          <div className="h-2 w-2 rounded-full bg-zinc-400" />
        </div>
      )
    default:
      return null
  }
}

export function AnnotatorBadges({
  assignments,
  maxVisible = 4,
  size = 'sm',
  showStatus = true,
  onUnassign,
  canUnassign = false,
  onAssign,
  canAssign = false,
}: AnnotatorBadgesProps) {
  const { t } = useI18n()

  if (!assignments || assignments.length === 0) {
    return (
      <button
        onClick={onAssign}
        disabled={!canAssign || !onAssign}
        className={`text-xs italic ${
          canAssign && onAssign
            ? 'cursor-pointer text-emerald-600 hover:text-emerald-700 hover:underline dark:text-emerald-400 dark:hover:text-emerald-300'
            : 'cursor-default text-zinc-400 dark:text-zinc-500'
        } transition-colors`}
      >
        {canAssign && onAssign ? t('projects.annotators.assign') : t('projects.annotators.unassigned')}
      </button>
    )
  }

  const sizeClasses = {
    xs: 'h-5 w-5 text-[10px]',
    sm: 'h-6 w-6 text-xs',
    md: 'h-8 w-8 text-sm',
    lg: 'h-10 w-10 text-base',
  }

  const visibleAssignments = assignments.slice(0, maxVisible)
  const remainingCount = assignments.length - maxVisible

  return (
    <div className="flex items-center -space-x-1">
      {visibleAssignments.map((assignment, index) => {
        const initials = getInitials(
          assignment.user_name,
          assignment.user_email
        )
        const displayName =
          assignment.user_name || assignment.user_email || t('projects.annotators.unknown')
        const colorClass = getUserColor(assignment.user_id)

        const tooltipContent = `${displayName}${
          assignment.status ? ` - ${assignment.status.replace('_', ' ')}` : ''
        }${
          assignment.priority && assignment.priority > 0
            ? ` (Priority: ${assignment.priority})`
            : ''
        }`

        return (
          <Tooltip key={assignment.id || index} content={tooltipContent}>
            <div className="group relative">
              <div
                className={` ${sizeClasses[size]} ${colorClass} relative flex items-center justify-center rounded-full font-semibold ring-2 ring-white transition-transform hover:z-10 hover:scale-110 dark:ring-zinc-900`}
              >
                {initials}
              </div>
              {showStatus && getStatusIndicator(assignment.status)}
              {canUnassign && onUnassign && (
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onUnassign(assignment.id)
                  }}
                  className="absolute -right-1 -top-1 z-20 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-xs text-white opacity-0 transition-colors hover:bg-red-600 group-hover:opacity-100"
                  title={t('projects.annotators.removeAssignment')}
                >
                  ×
                </button>
              )}
            </div>
          </Tooltip>
        )
      })}

      {remainingCount > 0 && (
        <Tooltip
          content={`+${remainingCount} more: ${assignments
            .slice(maxVisible)
            .map((a) => a.user_name || a.user_email || t('projects.annotators.unknown'))
            .join(', ')}`}
        >
          <div
            className={` ${sizeClasses[size]} relative flex items-center justify-center rounded-full bg-zinc-200 font-semibold text-zinc-700 ring-2 ring-white transition-transform hover:z-10 hover:scale-110 dark:bg-zinc-700 dark:text-zinc-300 dark:ring-zinc-900`}
          >
            +{remainingCount}
          </div>
        </Tooltip>
      )}
    </div>
  )
}
