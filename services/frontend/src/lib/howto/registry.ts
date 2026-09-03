/**
 * How-To guide registry.
 *
 * The /how-to page renders the platform's own guides plus whatever the
 * extended package registers here during initialization (student-surface
 * guides, Vertretbar-specific answers). Bilingual copy is kept inline, like
 * the changelog entries, so a guide is one self-contained object that is
 * easy to review and to keep in sync with the feature it documents.
 *
 * The same registry feeds the nav-bar search: every guide is a searchable
 * result that deep-links to its anchor on /how-to.
 */

import { useEffect, useState } from 'react'

export type HowToLocale = 'de' | 'en'
export type Bilingual = { de: string; en: string }
export type BilingualList = { de: string[]; en: string[] }

export type HowToCategoryId =
  | 'start'
  | 'organizations'
  | 'projects'
  | 'data'
  | 'annotation'
  | 'generation'
  | 'evaluation'
  | 'integrations'
  | 'student'
  | 'troubleshooting'

export interface HowToCategory {
  id: HowToCategoryId
  title: Bilingual
  /** One line under the category heading. */
  blurb: Bilingual
}

export interface HowToLink {
  label: Bilingual
  href: string
}

export interface HowToGuide {
  /** Stable anchor id, kebab-case; deep link is /how-to#<id>. */
  id: string
  category: HowToCategoryId
  /** Question-style title ("Wie lade ich Daten hoch?") — what users search for. */
  title: Bilingual
  /** One or two sentences: the short answer. */
  summary: Bilingual
  /** Numbered steps. Inline `code`, **bold** and [label](/path) are rendered. */
  steps?: BilingualList
  /** "Gut zu wissen" bullets. */
  tips?: BilingualList
  /** "Typische Stolpersteine" bullets. */
  pitfalls?: BilingualList
  /** Related pages / guides (guide anchors as /how-to#id). */
  links?: HowToLink[]
  /** Extra search terms (synonyms, old names, English/German variants). */
  keywords?: BilingualList
}

/** Category order = page order. */
export const HOWTO_CATEGORIES: HowToCategory[] = [
  {
    id: 'start',
    title: { de: 'Erste Schritte', en: 'Getting started' },
    blurb: {
      de: 'Was BenGER und Vertretbar sind, wie Sie sich zurechtfinden und was Sie zuerst einrichten sollten.',
      en: 'What BenGER and Vertretbar are, how to find your way around, and what to set up first.',
    },
  },
  {
    id: 'organizations',
    title: { de: 'Organisationen, Gruppen & Einladungen', en: 'Organizations, groups & invitations' },
    blurb: {
      de: 'Mitglieder, Rollen, Gruppen (z.B. Lehrstühle) und Einladungslinks.',
      en: 'Members, roles, groups (e.g. chairs) and invitation links.',
    },
  },
  {
    id: 'projects',
    title: { de: 'Projekte anlegen & konfigurieren', en: 'Creating & configuring projects' },
    blurb: {
      de: 'Der Projekt-Assistent, Projekttypen, Einstellungen und die Projektseite.',
      en: 'The project wizard, project types, settings and the project page.',
    },
  },
  {
    id: 'data',
    title: { de: 'Daten hochladen, importieren & exportieren', en: 'Uploading, importing & exporting data' },
    blurb: {
      de: 'Dateiformate, Feldzuordnung und der Projekt-Export/-Import.',
      en: 'File formats, field mapping and project export/import.',
    },
  },
  {
    id: 'annotation',
    title: { de: 'Annotationsoberfläche & XML', en: 'Annotation interface & XML' },
    blurb: {
      de: 'Die Oberfläche, die Annotierende sehen, und wie Sie das XML dahinter anpassen.',
      en: 'The interface annotators see, and how to edit the XML behind it.',
    },
  },
  {
    id: 'generation',
    title: { de: 'KI-Modelle & Generierung', en: 'AI models & generation' },
    blurb: {
      de: 'API-Schlüssel, eigene Modelle, Prompts und Generierungsläufe.',
      en: 'API keys, custom models, prompts and generation runs.',
    },
  },
  {
    id: 'evaluation',
    title: { de: 'Evaluation, Korrektur & Berichte', en: 'Evaluation, grading & reports' },
    blurb: {
      de: 'Bewertungsverfahren, Sofort-Evaluation, menschliche Korrektur, Berichte und Bestenlisten.',
      en: 'Evaluation methods, immediate evaluation, human grading, reports and leaderboards.',
    },
  },
  {
    id: 'integrations',
    title: { de: 'Integrationen (Moodle, ILIAS, LTI)', en: 'Integrations (Moodle, ILIAS, LTI)' },
    blurb: {
      de: 'BenGER-Klausuren in Lernplattformen einbinden.',
      en: 'Embedding BenGER exams in learning platforms.',
    },
  },
  {
    id: 'student',
    title: { de: 'Für Studierende', en: 'For students' },
    blurb: {
      de: 'Klausuren üben, Karteikarten lernen, Ergebnisse verstehen.',
      en: 'Practising exams, learning with flashcards, understanding results.',
    },
  },
  {
    id: 'troubleshooting',
    title: { de: 'Probleme lösen', en: 'Troubleshooting' },
    blurb: {
      de: 'Die häufigsten Fehlermeldungen und was dahintersteckt.',
      en: 'The most common error messages and what is behind them.',
    },
  },
]

const buckets: Record<string, HowToGuide[]> = {}
const listeners: Set<() => void> = new Set()

function notifyListeners() {
  listeners.forEach((fn) => fn())
}

/**
 * Register guides under a named source. Re-registering the same source
 * replaces its guides (idempotent), so tests and a repeated loadExtended()
 * never duplicate entries.
 */
export function registerHowToGuides(source: string, guides: HowToGuide[]) {
  buckets[source] = guides
  notifyListeners()
}

/** All registered guides in category order, sources in registration order. */
export function getHowToGuides(): HowToGuide[] {
  const order = new Map(HOWTO_CATEGORIES.map((c, i) => [c.id, i]))
  return Object.values(buckets)
    .flat()
    .sort((a, b) => (order.get(a.category) ?? 99) - (order.get(b.category) ?? 99))
}

/** React hook: all guides, re-rendering when a source registers later. */
export function useHowToGuides(): HowToGuide[] {
  const [, setTick] = useState(0)
  useEffect(() => {
    const listener = () => setTick((t) => t + 1)
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])
  return getHowToGuides()
}

export function pick(text: Bilingual, locale: string): string {
  return locale === 'en' ? text.en : text.de
}

export function pickList(list: BilingualList | undefined, locale: string): string[] {
  if (!list) return []
  return locale === 'en' ? list.en : list.de
}

/** Plain text of guide copy: drops `code`, **bold**, *italic* markers and link targets. */
export function stripInlineMarkup(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*\s][^*]*)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
}

/** Lower-cased, diacritics-folded text for matching (ä→a, ß→ss). */
export function normalizeForSearch(text: string): string {
  return text
    .toLowerCase()
    .replace(/ß/g, 'ss')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
}

/** Every word of a guide in one locale, used by the page filter and the nav search. */
export function guideSearchText(guide: HowToGuide, locale: string): string {
  const parts = [
    pick(guide.title, locale),
    pick(guide.summary, locale),
    ...pickList(guide.steps, locale),
    ...pickList(guide.tips, locale),
    ...pickList(guide.pitfalls, locale),
    ...pickList(guide.keywords, locale),
    // Keywords of the other language too: users mix German and English.
    ...pickList(guide.keywords, locale === 'en' ? 'de' : 'en'),
  ]
  return normalizeForSearch(stripInlineMarkup(parts.join(' ')))
}
