'use client'

import { useState } from 'react'

import { Button } from '@/components/shared/Button'
import { Dialog } from '@/components/shared/Dialog'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import { useI18n } from '@/contexts/I18nContext'
import { getRegisteredWizardProjectTypes } from '@/lib/extensions/wizardTemplates'
import {
  DEFAULT_JURISDICTION,
  offeredFor,
  type Jurisdiction,
} from '@/lib/jurisdiction'
import { defaultIconForKind } from '@/lib/projectKind'
import { cn } from '@/lib/utils'

import type { WizardProjectKind } from './types'

export const PROJECT_KIND_OPTIONS: {
  id: WizardProjectKind
  icon: string
  nameKey: string
  descriptionKey: string
}[] = [
  {
    id: 'generic',
    icon: '🗂️',
    nameKey: 'projects.creation.wizard.step1.kind.generic',
    descriptionKey: 'projects.creation.wizard.step1.kind.genericDescription',
  },
  {
    id: 'exam',
    icon: '⚖️',
    nameKey: 'projects.creation.wizard.step1.kind.exam',
    descriptionKey: 'projects.creation.wizard.step1.kind.examDescription',
  },
  {
    id: 'flashcard_collection',
    icon: '🗃️',
    nameKey: 'projects.creation.wizard.step1.kind.deck',
    descriptionKey: 'projects.creation.wizard.step1.kind.deckDescription',
  },
]

/** Curated emoji set for the picker; any other emoji can be typed. */
export const ICON_CHOICES = [
  '⚖️',
  '📚',
  '🗃️',
  '📝',
  '🎓',
  '🏛️',
  '📜',
  '🔍',
  '🧠',
  '💡',
  '🧪',
  '📊',
  '🗂️',
  '🏷️',
  '🎯',
  '🧩',
]

export { defaultIconForKind } from '@/lib/projectKind'

/**
 * Compact project-type selector. The three base kinds are always shown;
 * extensions add more options with `registerWizardProjectType` (e.g. the
 * French exam types for 'FR' organizations), each created as one of the
 * base kinds. Registered types of other jurisdictions sit behind a "show
 * all" toggle: an organization's jurisdiction is only its default, and
 * groups inside it may teach another legal system (e.g. a French-law group
 * in a German faculty). The type drives discoverability, the deck workspace and the
 * student surfaces; it can be changed later in the project details (except
 * on student-created projects). Option descriptions surface as tooltips and
 * under the selected option to keep the rows flat.
 */
export function ProjectTypeSelector({
  projectKind,
  projectTypeId,
  jurisdictions = [DEFAULT_JURISDICTION],
  onChange,
}: {
  projectKind: WizardProjectKind
  projectTypeId?: string
  jurisdictions?: ReadonlyArray<Jurisdiction>
  onChange: (partial: {
    projectKind: WizardProjectKind
    projectTypeId: string
  }) => void
}) {
  const { t } = useI18n()
  const registered = getRegisteredWizardProjectTypes()
  const offered = registered.filter((r) =>
    offeredFor(r.jurisdictions, jurisdictions),
  )
  const others = registered.filter((r) => !offered.includes(r))
  const selectedId = projectTypeId ?? projectKind
  // Opens expanded when the selected type is one of the other jurisdictions.
  const [showAll, setShowAll] = useState(() =>
    others.some((r) => r.id === selectedId),
  )
  const options: {
    id: string
    kind: WizardProjectKind
    icon: string
    nameKey: string
    descriptionKey: string
  }[] = [
    ...PROJECT_KIND_OPTIONS.map((o) => ({ ...o, kind: o.id })),
    ...offered,
    // Collapsed, a selected type of another jurisdiction stays visible.
    ...others.filter((r) => showAll || r.id === selectedId),
  ]
  const selected = options.find((o) => o.id === selectedId)
  return (
    <div data-testid="project-type-and-icon">
      <Label>
        {t('projects.creation.wizard.step1.kind.title')}{' '}
        <span className="text-red-600 dark:text-red-400">*</span>
      </Label>
      <div
        className="mt-2 grid grid-cols-3 gap-2"
        role="radiogroup"
        aria-label={t('projects.creation.wizard.step1.kind.title')}
      >
        {options.map((opt) => {
          const isSelected = selectedId === opt.id
          return (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={isSelected}
              title={t(opt.descriptionKey)}
              onClick={() =>
                onChange({ projectKind: opt.kind, projectTypeId: opt.id })
              }
              data-testid={`project-kind-${opt.id}`}
              className={cn(
                'flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500',
                isSelected
                  ? 'border-emerald-500 bg-emerald-50 text-zinc-900 ring-1 ring-emerald-500 dark:bg-emerald-900/20 dark:text-white'
                  : 'border-zinc-200 text-zinc-700 hover:border-zinc-300 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-zinc-600',
              )}
            >
              <span className="text-lg" aria-hidden>
                {opt.icon}
              </span>
              {t(opt.nameKey)}
            </button>
          )
        })}
      </div>
      {others.length > 0 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          aria-expanded={showAll}
          data-testid="project-kind-show-all"
          className="mt-2 rounded-full border border-zinc-200 px-3 py-1 text-xs font-medium text-zinc-600 transition-colors hover:border-zinc-300 hover:text-zinc-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:border-zinc-700 dark:text-zinc-400 dark:hover:border-zinc-600 dark:hover:text-white"
        >
          {showAll
            ? t('projects.creation.wizard.step1.kind.showLess')
            : t('projects.creation.wizard.step1.kind.showAll', {
                count: others.length,
              })}
        </button>
      )}
      <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
        {selected ? `${t(selected.descriptionKey)} · ` : ''}
        {t('projects.creation.wizard.step1.kind.locked')}
      </p>
    </div>
  )
}

/**
 * Emoji picker dialog for the project icon (opened from the icon button next
 * to the wizard heading). Curated grid + free-text input for any emoji.
 */
export function IconPickerModal({
  isOpen,
  onClose,
  icon,
  projectKind,
  onPick,
}: {
  isOpen: boolean
  onClose: () => void
  icon: string
  projectKind: WizardProjectKind
  onPick: (icon: string) => void
}) {
  const { t } = useI18n()
  const [draft, setDraft] = useState(icon)
  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title={t('projects.creation.wizard.step1.icon.title')}
    >
      <div className="space-y-4" data-testid="icon-picker-modal">
        <div
          className="flex flex-wrap gap-2"
          data-testid="project-icon-choices"
        >
          {ICON_CHOICES.map((e) => (
            <button
              key={e}
              type="button"
              onClick={() => setDraft(e)}
              aria-pressed={draft === e}
              data-testid={`project-icon-${e}`}
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-md border text-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500',
                draft === e
                  ? 'border-emerald-500 bg-emerald-50 ring-1 ring-emerald-500 dark:bg-emerald-900/20'
                  : 'border-zinc-200 hover:border-zinc-300 dark:border-zinc-700 dark:hover:border-zinc-600',
              )}
            >
              {e}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <span className="inline-block w-24">
            <Input
              value={draft}
              maxLength={8}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={defaultIconForKind(
                projectKind === 'generic' ? null : projectKind,
              )}
              className="text-center text-xl"
              data-testid="project-icon-input"
            />
          </span>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {t('projects.creation.wizard.step1.icon.help')}
          </p>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            variant="filled"
            data-testid="project-icon-save"
            onClick={() => {
              onPick(
                draft.trim() ||
                  defaultIconForKind(
                    projectKind === 'generic' ? null : projectKind,
                  ),
              )
              onClose()
            }}
          >
            {t('common.save')}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}

export default ProjectTypeSelector
