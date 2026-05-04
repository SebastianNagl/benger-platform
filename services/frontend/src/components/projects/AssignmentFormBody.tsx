/**
 * Shared assignment form body — used by both TaskAssignmentModal (annotation
 * task assignment) and AssignKorrekturModal (Korrektur item assignment) so the
 * two surfaces stay in sync. Owns no submit logic; the parent wraps it with
 * its own Save handler.
 */

'use client'

import { TableCheckbox } from '@/components/projects/TableCheckbox'
import { UserAvatar } from '@/components/projects/UserAvatar'
import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import {
  ArrowPathRoundedSquareIcon,
  ChartBarIcon,
  SparklesIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'

export type AssignmentDistribution =
  | 'manual'
  | 'round_robin'
  | 'random'
  | 'load_balanced'

export interface AssignmentMember {
  id?: string
  user_id: string
  name: string
  email?: string
  role: string
}

export interface AssignmentFormValue {
  user_ids: string[]
  distribution: AssignmentDistribution
  priority: number
  due_date: string // YYYY-MM-DDTHH:mm or ''
  notes: string
}

export const EMPTY_ASSIGNMENT_FORM: AssignmentFormValue = {
  user_ids: [],
  distribution: 'manual',
  priority: 0,
  due_date: '',
  notes: '',
}

interface Props {
  members: AssignmentMember[]
  value: AssignmentFormValue
  onChange: (next: AssignmentFormValue) => void
  /** When false, hides the distribution dropdown (e.g. single-target assignment). */
  showDistribution?: boolean
  /** Override which member roles are selectable. Defaults to annotation-task roles. */
  eligibleRoles?: Set<string>
}

const DEFAULT_ELIGIBLE_ROLES = new Set([
  'ANNOTATOR',
  'REVIEWER',
  'CONTRIBUTOR',
  'ORG_ADMIN',
  'annotator',
  'reviewer',
  'contributor',
  'org_admin',
])

export const KORREKTUR_ELIGIBLE_ROLES = new Set([
  'CONTRIBUTOR',
  'ORG_ADMIN',
  'ADMIN',
  'contributor',
  'org_admin',
  'admin',
])

function distributionIcon(d: AssignmentDistribution) {
  switch (d) {
    case 'manual':
      return <UserGroupIcon className="h-5 w-5" />
    case 'round_robin':
      return <ArrowPathRoundedSquareIcon className="h-5 w-5" />
    case 'random':
      return <SparklesIcon className="h-5 w-5" />
    case 'load_balanced':
      return <ChartBarIcon className="h-5 w-5" />
  }
}

export function AssignmentFormBody({
  members,
  value,
  onChange,
  showDistribution = true,
  eligibleRoles = DEFAULT_ELIGIBLE_ROLES,
}: Props) {
  const { t } = useI18n()

  const uniqueMembers = Array.from(
    new Map(members.map((m) => [m.user_id, m])).values(),
  )
  const annotators = uniqueMembers.filter((m) => eligibleRoles.has(m.role))

  const toggleUser = (userId: string) => {
    const has = value.user_ids.includes(userId)
    onChange({
      ...value,
      user_ids: has
        ? value.user_ids.filter((id) => id !== userId)
        : [...value.user_ids, userId],
    })
  }

  const toggleAll = () => {
    onChange({
      ...value,
      user_ids:
        value.user_ids.length === annotators.length
          ? []
          : annotators.map((a) => a.user_id),
    })
  }

  const distributionDescription = {
    manual: t('projects.taskAssignment.manualDescription'),
    round_robin: t('projects.taskAssignment.roundRobinDescription'),
    random: t('projects.taskAssignment.randomDescription'),
    load_balanced: t('projects.taskAssignment.loadBalancedDescription'),
  }[value.distribution]

  return (
    <div className="space-y-6">
      {showDistribution && (
        <div>
          <Label>{t('projects.taskAssignment.distributionMethod')}</Label>
          <Select
            value={value.distribution}
            onValueChange={(v) => onChange({ ...value, distribution: v as AssignmentDistribution })}
          >
            <SelectTrigger>
              <div className="flex items-center gap-2">
                {distributionIcon(value.distribution)}
                <SelectValue />
              </div>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="manual">{t('projects.taskAssignment.manual')}</SelectItem>
              <SelectItem value="round_robin">{t('projects.taskAssignment.roundRobin')}</SelectItem>
              <SelectItem value="random">{t('projects.taskAssignment.random')}</SelectItem>
              <SelectItem value="load_balanced">{t('projects.taskAssignment.loadBalanced')}</SelectItem>
            </SelectContent>
          </Select>
          <p className="mt-1 text-xs text-zinc-500">{distributionDescription}</p>
        </div>
      )}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <Label>{t('projects.taskAssignment.selectAnnotators')}</Label>
          <Button variant="text" onClick={toggleAll}>
            {value.user_ids.length === annotators.length
              ? t('projects.taskAssignment.deselectAll')
              : t('projects.taskAssignment.selectAll')}
          </Button>
        </div>

        <div className="max-h-48 divide-y overflow-y-auto rounded-lg border">
          {annotators.length === 0 ? (
            <div className="p-4 text-center text-sm text-zinc-500">
              {t('tasks.assignment.noUsers')}
            </div>
          ) : (
            annotators.map((m) => (
              <div
                key={m.user_id}
                className="flex cursor-pointer items-center gap-3 p-3 hover:bg-zinc-50 dark:hover:bg-zinc-800"
                onClick={() => toggleUser(m.user_id)}
              >
                <TableCheckbox
                  checked={value.user_ids.includes(m.user_id)}
                  onChange={() => {}}
                />
                <UserAvatar name={m.name} email={m.email ?? ''} size="sm" />
                <div className="flex-1">
                  <div className="text-sm font-medium">{m.name}</div>
                  {m.email && (
                    <div className="text-xs text-zinc-500">{m.email}</div>
                  )}
                </div>
                <div className="text-xs text-zinc-500">{m.role}</div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <Label htmlFor="priority">{t('projects.taskAssignment.priority')}</Label>
          <Select
            value={value.priority.toString()}
            onValueChange={(v) => onChange({ ...value, priority: parseInt(v) })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="0">{t('projects.taskAssignment.priorityNormal')}</SelectItem>
              <SelectItem value="1">{t('projects.taskAssignment.priorityLow')}</SelectItem>
              <SelectItem value="2">{t('projects.taskAssignment.priorityMedium')}</SelectItem>
              <SelectItem value="3">{t('projects.taskAssignment.priorityHigh')}</SelectItem>
              <SelectItem value="4">{t('projects.taskAssignment.priorityUrgent')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div>
          <Label htmlFor="due_date">
            {t('tasks.assignment.dueDate')} ({t('tasks.assignment.optional')})
          </Label>
          <Input
            id="due_date"
            type="datetime-local"
            value={value.due_date}
            onChange={(e) => onChange({ ...value, due_date: e.target.value })}
          />
        </div>
      </div>

      <div>
        <Label htmlFor="notes">
          {t('common.notes')} ({t('tasks.assignment.optional')})
        </Label>
        <Textarea
          id="notes"
          value={value.notes}
          onChange={(e) => onChange({ ...value, notes: e.target.value })}
          placeholder={t('projects.taskAssignment.notesPlaceholder')}
          rows={3}
        />
      </div>
    </div>
  )
}
