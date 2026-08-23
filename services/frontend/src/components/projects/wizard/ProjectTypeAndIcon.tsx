'use client'

import { useState } from 'react'
import { LockClosedIcon } from '@heroicons/react/24/outline'

import { Dialog } from '@/components/shared/Dialog'
import { Input } from '@/components/shared/Input'
import { Button } from '@/components/shared/Button'
import { Label } from '@/components/shared/Label'
import { useI18n } from '@/contexts/I18nContext'
import { defaultIconForKind } from '@/lib/projectKind'
import { cn } from '@/lib/utils'

import type { WizardProjectKind } from './types'

export const PROJECT_KIND_OPTIONS: {
  id: WizardProjectKind
  icon: string
  nameKey: string
  descriptionKey: string
  nameFallback: string
  descriptionFallback: string
}[] = [
  {
    id: 'generic',
    icon: '🗂️',
    nameKey: 'projects.creation.wizard.step1.kind.generic',
    descriptionKey: 'projects.creation.wizard.step1.kind.genericDescription',
    nameFallback: 'Generisch',
    descriptionFallback: 'Benchmark-/Annotationsprojekt ohne Klausur- oder Karten-Logik',
  },
  {
    id: 'exam',
    icon: '⚖️',
    nameKey: 'projects.creation.wizard.step1.kind.exam',
    descriptionKey: 'projects.creation.wizard.step1.kind.examDescription',
    nameFallback: 'Klausur',
    descriptionFallback: 'Falllösung mit Angabe, Musterlösung und KI-Korrektur; für Studierende lösbar',
  },
  {
    id: 'flashcard_collection',
    icon: '🗃️',
    nameKey: 'projects.creation.wizard.step1.kind.deck',
    descriptionKey: 'projects.creation.wizard.step1.kind.deckDescription',
    nameFallback: 'Kartenstapel',
    descriptionFallback: 'Karteikarten mit Vorder-/Rückseite und Lernplan (SRS)',
  },
]

/** Curated emoji set for the picker; any other emoji can be typed. */
export const ICON_CHOICES = [
  '⚖️', '📚', '🗃️', '📝', '🎓', '🏛️', '📜', '🔍', '🧠', '💡', '🧪', '📊', '🗂️', '🏷️', '🎯', '🧩',
]

export { defaultIconForKind } from '@/lib/projectKind'

/**
 * Compact one-row project-type selector. The type is write-once — it drives
 * discoverability, the deck workspace and the student surfaces — hence the
 * lock note. Option descriptions surface as tooltips and under the selected
 * option to keep the row height flat.
 */
export function ProjectTypeSelector({
  projectKind,
  onChange,
}: {
  projectKind: WizardProjectKind
  onChange: (partial: { projectKind: WizardProjectKind }) => void
}) {
  const { t } = useI18n()
  const selected = PROJECT_KIND_OPTIONS.find((o) => o.id === projectKind)
  return (
    <div data-testid="project-type-and-icon">
      <Label>
        {t('projects.creation.wizard.step1.kind.title', 'Projekttyp')}{' '}
        <span className="text-red-600 dark:text-red-400">*</span>
      </Label>
      <div className="mt-2 grid grid-cols-3 gap-2" role="radiogroup">
        {PROJECT_KIND_OPTIONS.map((opt) => {
          const isSelected = projectKind === opt.id
          return (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={isSelected}
              title={t(opt.descriptionKey, opt.descriptionFallback)}
              onClick={() => onChange({ projectKind: opt.id })}
              data-testid={`project-kind-${opt.id}`}
              className={cn(
                'flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors',
                isSelected
                  ? 'border-emerald-500 bg-emerald-50 text-zinc-900 ring-1 ring-emerald-500 dark:bg-emerald-900/20 dark:text-white'
                  : 'border-zinc-200 text-zinc-700 hover:border-zinc-300 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-zinc-600'
              )}
            >
              <span className="text-lg" aria-hidden>
                {opt.icon}
              </span>
              {t(opt.nameKey, opt.nameFallback)}
            </button>
          )
        })}
      </div>
      <p className="mt-2 flex items-center gap-1 text-xs text-zinc-500 dark:text-zinc-400">
        <LockClosedIcon className="h-3.5 w-3.5 shrink-0" />
        {selected ? `${t(selected.descriptionKey, selected.descriptionFallback)} · ` : ''}
        {t(
          'projects.creation.wizard.step1.kind.locked',
          'Wird bei der Erstellung festgelegt und kann danach nicht geändert werden.'
        )}
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
      title={t('projects.creation.wizard.step1.icon.title', 'Symbol wählen')}
    >
      <div className="space-y-4" data-testid="icon-picker-modal">
        <div className="flex flex-wrap gap-2" data-testid="project-icon-choices">
          {ICON_CHOICES.map((e) => (
            <button
              key={e}
              type="button"
              onClick={() => setDraft(e)}
              aria-pressed={draft === e}
              data-testid={`project-icon-${e}`}
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-md border text-xl',
                draft === e
                  ? 'border-emerald-500 bg-emerald-50 ring-1 ring-emerald-500 dark:bg-emerald-900/20'
                  : 'border-zinc-200 hover:border-zinc-300 dark:border-zinc-700 dark:hover:border-zinc-600'
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
              placeholder={defaultIconForKind(projectKind === 'generic' ? null : projectKind)}
              className="text-center text-xl"
              data-testid="project-icon-input"
            />
          </span>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {t(
              'projects.creation.wizard.step1.icon.help',
              'Wird in Listen, im Projektkopf und unter „Entdecken“ angezeigt.'
            )}
          </p>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel', 'Abbrechen')}
          </Button>
          <Button
            variant="filled"
            data-testid="project-icon-save"
            onClick={() => {
              onPick(
                draft.trim() ||
                  defaultIconForKind(projectKind === 'generic' ? null : projectKind)
              )
              onClose()
            }}
          >
            {t('common.save', 'Speichern')}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}

export default ProjectTypeSelector
