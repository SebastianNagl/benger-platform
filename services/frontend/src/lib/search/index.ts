/**
 * Nav-bar search index: every page a user can reach plus every how-to
 * guide, with the ranking that turns a free-text query into results.
 *
 * Kept outside the Search component so the page list has one place to be
 * maintained and can be unit-tested without the autocomplete plumbing.
 * Add a route here whenever a user-facing page is added.
 */

import {
  getHowToGuides,
  guideSearchText,
  normalizeForSearch,
  pick,
  stripInlineMarkup,
  type HowToGuide,
} from '@/lib/howto'
import type { Result } from '@/types/search'

// Side-effect import: registers the platform guides so the index is complete
// even before /how-to was ever visited.
import '@/data/howto/guides'

type Translate = (key: string, fallback?: string) => string

export interface SearchIndexContext {
  t: Translate
  locale: string
  flags: Record<string, boolean> | null | undefined
  user: { is_superadmin?: boolean } | null | undefined
  organizations: Array<{ role?: string }> | null | undefined
  /** Injected for tests; defaults to the registry. */
  guides?: HowToGuide[]
}

export interface SearchEntry extends Result {
  /** Extra match terms, normalized. Not displayed. */
  keywords?: string
}

function page(
  t: Translate,
  url: string,
  key: string,
  category: string,
  keywords?: string,
): SearchEntry {
  return {
    url,
    title: t(`search.pages.${key}.title`),
    description: t(`search.pages.${key}.description`),
    category,
    keywords: keywords ? normalizeForSearch(keywords) : undefined,
  }
}

/** Static pages the current user may open, honoring feature flags and roles. */
export function buildPageIndex(ctx: SearchIndexContext): SearchEntry[] {
  const { t, flags, user, organizations } = ctx
  const cat = {
    benger: t('search.categories.benger'),
    projects: t('search.categories.projectsAndData'),
    knowledge: t('search.categories.knowledge'),
    user: t('search.categories.user'),
    org: t('search.categories.organizations', 'Organisation'),
    admin: t('search.categories.administration'),
  }
  const isSuperadmin = Boolean(user?.is_superadmin)
  const isOrgAdmin =
    isSuperadmin || Boolean(organizations?.some((org) => org.role === 'ORG_ADMIN'))

  const pages: SearchEntry[] = [
    page(t, '/', 'landing', cat.benger, 'start home landing startseite'),
    page(t, '/dashboard', 'dashboard', cat.benger, 'übersicht overview home'),
  ]
  if (flags?.reports) pages.push(page(t, '/reports', 'reports', cat.benger, 'berichte report pdf csv export'))
  if (flags?.leaderboards) {
    pages.push(page(t, '/leaderboards', 'leaderboards', cat.benger, 'bestenliste rangliste ranking annotatoren llm co-creation'))
  }
  if (user) {
    pages.push(page(t, '/runs', 'runs', cat.benger, 'läufe runs generierung evaluation status fortschritt'))
    pages.push(page(t, '/learning-stats', 'learningStats', cat.benger, 'lernstatistik statistik fällig karteikarten klausuren notenverlauf'))
  }
  pages.push(page(t, '/architecture', 'architecture', cat.benger, 'architektur technik aufbau'))
  pages.push(page(t, '/changelog', 'changelog', cat.benger, 'änderungen neuigkeiten changelog updates version'))

  pages.push(
    page(t, '/projects', 'projects', cat.projects, 'projekte projekt klausur kartenstapel'),
    page(t, '/projects/create', 'createProject', cat.projects, 'neues projekt anlegen erstellen assistent wizard klausur'),
    page(t, '/projects/archived', 'archivedProjects', cat.projects, 'archiv archiviert archivierte projekte'),
  )
  if (flags?.data) pages.push(page(t, '/data', 'dataManagement', cat.projects, 'daten upload import export csv json'))
  if (flags?.generations) pages.push(page(t, '/generations', 'generations', cat.projects, 'generierung generierungen llm prompt modelle'))
  if (flags?.evaluations) {
    pages.push(
      page(t, '/evaluations', 'evaluations', cat.projects, 'evaluation evaluierung bewertung metriken judge'),
      page(t, '/evaluations/human/likert', 'humanLikert', cat.projects, 'menschliche bewertung likert skala human evaluation'),
      page(t, '/evaluations/human/preference', 'humanPreference', cat.projects, 'menschliche bewertung präferenz vergleich a/b human evaluation'),
    )
  }

  if (flags?.['how-to']) pages.push(page(t, '/how-to', 'howTo', cat.knowledge, 'anleitung anleitungen hilfe help faq guide tutorial'))
  pages.push(page(t, '/models', 'models', cat.knowledge, 'modelle llm modellkatalog eigene modelle byom custom model preise'))

  pages.push(
    page(t, '/profile', 'profile', cat.user, 'profil konto account pseudonym passwort sprache oberfläche'),
    page(t, '/settings/notifications', 'notificationSettings', cat.user, 'benachrichtigungen einstellungen e-mail'),
    page(t, '/notifications', 'notifications', cat.user, 'benachrichtigungen mitteilungen inbox'),
    page(t, '/settings/models', 'modelSettings', cat.user, 'api-schlüssel api key openai anthropic provider schlüssel modelle'),
    page(t, '/users-organizations', 'usersOrganizations', cat.org, 'benutzer organisationen mitglieder einladen einladung gruppen rollen'),
  )
  if (isOrgAdmin) {
    pages.push(page(t, '/organizations', 'organizations', cat.org, 'organisation verwalten mitglieder rollen gruppen api-schlüssel einladung lti'))
  }
  if (isSuperadmin) {
    pages.push(
      page(t, '/admin/users', 'userManagement', cat.admin, 'benutzerverwaltung admin users'),
      page(t, '/admin/users-organizations', 'adminUsersOrganizations', cat.admin, 'admin benutzer organisationen'),
      page(t, '/admin/feature-flags', 'featureFlags', cat.admin, 'feature flags funktionen freischalten'),
      page(t, '/admin/lti', 'lti', cat.admin, 'lti moodle ilias integration registrierung'),
      page(t, '/admin/email-verification', 'emailVerification', cat.admin, 'e-mail verifizierung admin'),
      page(t, '/projects/deleted', 'deletedProjects', cat.admin, 'gelöschte projekte papierkorb wiederherstellen'),
    )
  }
  return pages
}

/** Every registered how-to guide as a deep-linked result. */
export function buildGuideIndex(ctx: SearchIndexContext): SearchEntry[] {
  const { t, locale } = ctx
  const guides = ctx.guides ?? getHowToGuides()
  const category = t('search.categories.howto', 'Anleitung')
  return guides.map((g) => ({
    url: `/how-to#${g.id}`,
    title: pick(g.title, locale),
    description: stripInlineMarkup(pick(g.summary, locale)),
    category,
    keywords: guideSearchText(g, locale),
  }))
}

export function buildSearchIndex(ctx: SearchIndexContext): SearchEntry[] {
  return [...buildPageIndex(ctx), ...buildGuideIndex(ctx)]
}

// ---------------------------------------------------------------------------
// Ranking
// ---------------------------------------------------------------------------

/** Cross-language synonyms so a German query finds an English title and vice versa. */
export const CROSS_LANGUAGE_MAPPINGS: Record<string, string[]> = {
  about: ['über', 'ueber'],
  projects: ['projekte', 'projekt'],
  project: ['projekt'],
  tasks: ['aufgaben'],
  data: ['daten'],
  upload: ['hochladen', 'import'],
  import: ['importieren', 'hochladen'],
  export: ['exportieren'],
  management: ['verwaltung'],
  evaluation: ['evaluierung', 'bewertung', 'auswertung'],
  grading: ['korrektur', 'bewertung'],
  architecture: ['architektur'],
  profile: ['profil'],
  user: ['benutzer'],
  users: ['benutzer'],
  dashboard: ['übersicht'],
  landing: ['startseite', 'home'],
  reports: ['berichte', 'bericht'],
  report: ['bericht'],
  generations: ['generierungen', 'generierung'],
  generation: ['generierung'],
  'how-to': ['anleitung', 'anleitungen', 'hilfe'],
  howto: ['anleitung', 'anleitungen', 'hilfe'],
  help: ['hilfe', 'anleitung'],
  guide: ['anleitung', 'leitfaden'],
  guides: ['anleitungen'],
  organizations: ['organisationen', 'organisation'],
  organization: ['organisation'],
  group: ['gruppe'],
  groups: ['gruppen'],
  invite: ['einladen', 'einladung'],
  invitation: ['einladung'],
  key: ['schlüssel'],
  keys: ['schlüssel'],
  models: ['modelle', 'llm', 'sprachmodelle'],
  model: ['modell'],
  llm: ['modelle', 'sprachmodelle'],
  exam: ['klausur'],
  exams: ['klausuren'],
  flashcards: ['karteikarten'],
  leaderboard: ['bestenliste', 'rangliste'],
  leaderboards: ['bestenliste', 'rangliste'],
  settings: ['einstellungen'],
  notifications: ['benachrichtigungen'],
  annotation: ['annotation', 'annotieren'],
  interface: ['oberfläche'],
  template: ['vorlage'],
  runs: ['läufe'],
  statistics: ['statistik'],

  über: ['about'],
  projekte: ['projects'],
  projekt: ['project'],
  aufgaben: ['tasks'],
  daten: ['data'],
  hochladen: ['upload', 'import'],
  importieren: ['import'],
  exportieren: ['export'],
  verwaltung: ['management', 'administration'],
  evaluierung: ['evaluation'],
  bewertung: ['evaluation', 'grading'],
  auswertung: ['evaluation'],
  korrektur: ['grading', 'correction'],
  architektur: ['architecture'],
  profil: ['profile'],
  benutzer: ['user', 'users'],
  übersicht: ['dashboard', 'overview'],
  startseite: ['landing', 'home'],
  berichte: ['reports'],
  bericht: ['report'],
  generierungen: ['generations'],
  generierung: ['generation'],
  anleitung: ['how-to', 'guide', 'help'],
  anleitungen: ['how-to', 'guides'],
  hilfe: ['help', 'how-to'],
  tutorial: ['how-to', 'guide'],
  organisationen: ['organizations'],
  organisation: ['organization'],
  gruppe: ['group'],
  gruppen: ['groups'],
  einladen: ['invite'],
  einladung: ['invitation', 'invite'],
  schlüssel: ['key', 'keys'],
  modelle: ['models', 'llm'],
  modell: ['model'],
  sprachmodelle: ['llm', 'models'],
  klausur: ['exam'],
  klausuren: ['exams'],
  karteikarten: ['flashcards'],
  bestenliste: ['leaderboard'],
  rangliste: ['leaderboard'],
  einstellungen: ['settings'],
  benachrichtigungen: ['notifications'],
  oberfläche: ['interface'],
  vorlage: ['template'],
  läufe: ['runs'],
  statistik: ['statistics'],
}

/** Fuzzy match for small typos (one substitution within the common prefix). */
export function isCloseMatch(word1: string, word2: string): boolean {
  if (Math.abs(word1.length - word2.length) > 2) return false
  let distance = 0
  const minLength = Math.min(word1.length, word2.length)
  for (let i = 0; i < minLength; i++) {
    if (word1[i] !== word2[i]) distance++
    if (distance > 2) return false
  }
  return distance <= 1
}

/** The query plus its cross-language variants (whole query and per word). */
export function expandQuery(query: string): string[] {
  const queryLower = query.toLowerCase()
  const expanded = [queryLower]
  Object.entries(CROSS_LANGUAGE_MAPPINGS).forEach(([term, translations]) => {
    if (queryLower.includes(term)) {
      translations.forEach((tr) => expanded.push(queryLower.replace(term, tr)))
    }
  })
  queryLower.split(/\s+/).forEach((word) => {
    if (CROSS_LANGUAGE_MAPPINGS[word]) expanded.push(...CROSS_LANGUAGE_MAPPINGS[word])
  })
  return [...new Set(expanded)]
}

export function scoreEntry(entry: SearchEntry, expandedQueries: string[]): number {
  let score = 0
  const title = entry.title.toLowerCase()
  const description = (entry.description ?? '').toLowerCase()
  const category = (entry.category ?? '').toLowerCase()
  const url = entry.url.toLowerCase()
  const titleWords = title.split(/\s+/)
  const descWords = description.split(/\s+/)
  const keywords = entry.keywords ?? ''

  expandedQueries.forEach((queryTerm) => {
    const q = queryTerm.toLowerCase()
    if (title === q) score += 100
    else if (title.includes(q)) score += 50
    if (description.includes(q)) score += 25
    if (category.includes(q)) score += 10
    if (url.includes(q)) score += 15
    const qNorm = normalizeForSearch(q)
    if (keywords && qNorm && keywords.includes(qNorm)) score += 20

    q.split(/\s+/).forEach((qWord) => {
      if (!qWord) return
      if (titleWords.some((w) => w.startsWith(qWord))) score += 15
      if (descWords.some((w) => w.startsWith(qWord))) score += 5
      if (titleWords.some((w) => isCloseMatch(w, qWord))) score += 8
      const wNorm = normalizeForSearch(qWord)
      if (keywords && wNorm.length > 2 && keywords.includes(wNorm)) score += 6
    })
  })
  return score
}

/** Rank entries for a query; entries without a positive score are dropped. */
export function rankSearchResults(
  entries: SearchEntry[],
  query: string,
  limit = 8,
): Result[] {
  const trimmed = query.trim()
  if (!trimmed) return []
  const expanded = expandQuery(trimmed)
  return entries
    .filter((e) => e.title && e.url && e.category)
    .map((e) => ({ entry: e, score: scoreEntry(e, expanded) }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(({ entry }) => {
      const { keywords: _keywords, ...result } = entry
      return result
    })
}
