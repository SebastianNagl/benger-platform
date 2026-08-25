'use client'

import type { Project } from '@/types/labelStudio'
import { PROJECT_KIND_OPTIONS } from '@/components/projects/wizard/ProjectTypeAndIcon'
import { SubSection } from '@/components/projects/SubSection'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'
import { cn } from '@/lib/utils'

interface ProjectKindSectionProps {
  project: Project
  /** Called with the new kind ('exam' | 'flashcard_collection' | null). */
  onKindChange: (kind: string | null) => void
}

/**
 * "Projekttyp" sub-section of the settings card: the editable kind radio —
 * the single source of truth for whether students can find the project as an
 * exam or flashcard deck. Changing the type never rewrites the project's
 * config (label config, judges, data stay untouched); instead the
 * `ProjectKindHints` slot underneath surfaces what is still missing for the
 * chosen experience to fully work (extended edition; empty in community).
 * The host gates rendering on edit permission + non-student origin.
 */
export function ProjectKindSection({ project, onKindChange }: ProjectKindSectionProps) {
  const { t } = useI18n()
  const KindHints = useSlot('ProjectKindHints')
  const currentKindId = project.kind ?? 'generic'
  return (
    <SubSection
      title={t('projects.creation.wizard.step1.kind.title', 'Projekttyp')}
      badge={t(
        PROJECT_KIND_OPTIONS.find((o) => o.id === currentKindId)?.nameKey ??
          'projects.creation.wizard.step1.kind.generic',
        PROJECT_KIND_OPTIONS.find((o) => o.id === currentKindId)?.nameFallback ?? 'Generisch',
      )}
    >
      <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
        {t(
          'projects.creation.wizard.step1.kind.editableHint',
          'Der Typ steuert, ob Studierende dieses Projekt als Klausur bzw. Kartenstapel finden können.'
        )}
      </p>
      <div
        className="grid grid-cols-3 gap-2"
        role="radiogroup"
        aria-label={t('projects.creation.wizard.step1.kind.title', 'Projekttyp')}
        data-testid="project-kind-section"
      >
        {PROJECT_KIND_OPTIONS.map((opt) => {
          const isSelected = currentKindId === opt.id
          return (
            <button
              key={opt.id}
              type="button"
              role="radio"
              aria-checked={isSelected}
              title={t(opt.descriptionKey, opt.descriptionFallback)}
              onClick={() => {
                if (isSelected) return
                onKindChange(opt.id === 'generic' ? null : opt.id)
              }}
              data-testid={`project-kind-${opt.id}`}
              className={cn(
                'flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500',
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
      {/* Extended edition: live "what's still missing" warnings for the
          chosen type (judge, Musterlösung, card data, …). */}
      {KindHints ? (
        // eslint-disable-next-line react-hooks/static-components
        <KindHints project={project} />
      ) : null}
    </SubSection>
  )
}
