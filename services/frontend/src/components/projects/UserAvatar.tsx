/**
 * User Avatar component for the Project Data Manager
 *
 * Displays user avatars with tooltips for annotators and reviewers
 */

interface UserAvatarProps {
  name: string
  email?: string
  size?: 'sm' | 'md' | 'lg'
  showTooltip?: boolean
}

const sizeClasses = {
  sm: 'h-6 w-6 text-xs',
  md: 'h-8 w-8 text-sm',
  lg: 'h-10 w-10 text-base',
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((word) => word.charAt(0))
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

function getAvatarColor(name: string): string {
  const colors = [
    'bg-red-500',
    'bg-orange-500',
    'bg-amber-500',
    'bg-yellow-500',
    'bg-lime-500',
    'bg-green-500',
    'bg-emerald-500',
    'bg-teal-500',
    'bg-cyan-500',
    'bg-sky-500',
    'bg-emerald-500',
    'bg-indigo-500',
    'bg-violet-500',
    'bg-purple-500',
    'bg-fuchsia-500',
    'bg-pink-500',
    'bg-rose-500',
  ]

  const index = name
    .split('')
    .reduce((acc, char) => acc + char.charCodeAt(0), 0)
  return colors[index % colors.length]
}

export function UserAvatar({
  name,
  email,
  size = 'md',
  showTooltip = true,
}: UserAvatarProps) {
  const initials = getInitials(name)
  const colorClass = getAvatarColor(name)
  const sizeClass = sizeClasses[size]

  const avatar = (
    <div
      className={`inline-flex items-center justify-center rounded-full font-medium text-white ${colorClass} ${sizeClass} cursor-pointer transition-opacity hover:opacity-80`}
      title={showTooltip ? `${name}${email ? ` (${email})` : ''}` : undefined}
    >
      {initials}
    </div>
  )

  if (!showTooltip) {
    return avatar
  }

  return (
    <div className="group relative">
      {avatar}
      <div className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2 transform whitespace-nowrap rounded bg-zinc-900 px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 dark:bg-zinc-700">
        {name}
        {email && (
          <div className="text-zinc-300 dark:text-zinc-400">{email}</div>
        )}
        <div className="absolute left-1/2 top-full -translate-x-1/2 transform border-4 border-transparent border-t-zinc-900 dark:border-t-zinc-700"></div>
      </div>
    </div>
  )
}
