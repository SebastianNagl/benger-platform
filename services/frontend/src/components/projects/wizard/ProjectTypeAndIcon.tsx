'use client'

import { LockClosedIcon } from '@heroicons/react/24/outline'

import { Input } from '@/components/shared/Input'
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

interface Props {
  projectKind: WizardProjectKind
  icon: string
  onChange: (partial: { projectKind?: WizardProjectKind; icon?: string }) => void
}

/**
 * Step 1 extras: the project type (write-once — it drives discoverability,
 * the deck workspace and the student surfaces) and a display emoji.
 */
export function ProjectTypeAndIcon({ projectKind, icon, onChange }: Props) {
  const { t } = useI18n()
  return (
    <div className="space-y-6" data-testid="project-type-and-icon">
      <div>
        <Label>
          {t('projects.creation.wizard.step1.kind.title', 'Projekttyp')}{' '}
          <span className="text-red-600 dark:text-red-400">*</span>
        </Label>
        <p className="mb-3 flex items-center gap-1 text-sm text-zinc-500 dark:text-zinc-400">
          <LockClosedIcon className="h-3.5 w-3.5" />
          {t(
            'projects.creation.wizard.step1.kind.locked',
            'Wird bei der Erstellung festgelegt und kann danach nicht geändert werden.'
          )}
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3" role="radiogroup">
          {PROJECT_KIND_OPTIONS.map((opt) => {
            const selected = projectKind === opt.id
            return (
              <button
                key={opt.id}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => onChange({ projectKind: opt.id })}
                data-testid={`project-kind-${opt.id}`}
                className={cn(
                  'rounded-lg border p-4 text-left transition-colors',
                  selected
                    ? 'border-emerald-500 bg-emerald-50 ring-1 ring-emerald-500 dark:bg-emerald-900/20'
                    : 'border-zinc-200 hover:border-zinc-300 dark:border-zinc-700 dark:hover:border-zinc-600'
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="text-xl" aria-hidden>
                    {opt.icon}
                  </span>
                  <span className="font-medium text-zinc-900 dark:text-white">
                    {t(opt.nameKey, opt.nameFallback)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                  {t(opt.descriptionKey, opt.descriptionFallback)}
                </p>
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <Label htmlFor="project-icon">
          {t('projects.creation.wizard.step1.icon.title', 'Symbol')}
          <span className="ml-2 text-sm text-zinc-500 dark:text-zinc-400">
            {t('projects.creation.wizard.step1.optional')}
          </span>
        </Label>
        <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="project-icon-choices">
          {ICON_CHOICES.map((e) => (
            <button
              key={e}
              type="button"
              onClick={() => onChange({ icon: icon === e ? '' : e })}
              aria-pressed={icon === e}
              data-testid={`project-icon-${e}`}
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-md border text-lg',
                icon === e
                  ? 'border-emerald-500 bg-emerald-50 ring-1 ring-emerald-500 dark:bg-emerald-900/20'
                  : 'border-zinc-200 hover:border-zinc-300 dark:border-zinc-700 dark:hover:border-zinc-600'
              )}
            >
              {e}
            </button>
          ))}
          <span className="inline-block w-20">
            <Input
              id="project-icon"
              value={icon}
              maxLength={8}
              onChange={(e) => onChange({ icon: e.target.value })}
              placeholder={defaultIconForKind(projectKind === 'generic' ? null : projectKind)}
              className="text-center text-lg"
              data-testid="project-icon-input"
            />
          </span>
        </div>
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
          {t(
            'projects.creation.wizard.step1.icon.help',
            'Wird in Listen, im Projektkopf und unter „Entdecken“ angezeigt. Ohne Auswahl gilt das Typ-Symbol.'
          )}
        </p>
      </div>
    </div>
  )
}

export default ProjectTypeAndIcon
