import type { ChangelogEntry } from '@/lib/extensions/changelog'

/**
 * Platform changelog entries, newest first. One short user-facing bullet
 * per meaningful change; both languages. Extended-edition entries live in
 * the extended package and are merged in via registerChangelogEntries().
 */
export const PLATFORM_CHANGELOG: ChangelogEntry[] = [
  {
    date: '2026-09-01',
    audience: 'benger',
    text: {
      de: 'Organisationen können Mitglieder, Projekte und API-Schlüssel jetzt in Gruppen (z.B. Lehrstühle) aufteilen — Gruppen sehen nur ihre eigenen Projekte und nutzen ihre eigenen Schlüssel; Gruppen-Admins verwalten ihre Gruppe selbst.',
      en: 'Organizations can now split members, projects, and API keys into groups (e.g. chairs) — groups only see their own projects and spend their own keys; group admins manage their group themselves.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Projektseite: neue Karte „Abrechnung" zeigt, wessen API-Schlüssel die KI-Auswertungen bezahlt.',
      en: 'Project page: new "Billing" card shows whose API key pays for AI evaluations.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Cloud-Speicher-Import: Organisationen können S3-kompatible Speicher verbinden; Dateien lassen sich direkt aus dem Bucket als Aufgaben importieren.',
      en: 'Cloud storage import: organizations can connect S3-compatible storage and import files from the bucket as tasks.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Projekt-Assistent: klarere Datenquellen-Auswahl — bei Klausur-Projekten steht „Klausur erfassen“ jetzt an erster Stelle, „Tabelle/JSON einfügen“ heißt, was es ist.',
      en: 'Project wizard: clearer data-source picker — for exam projects "Enter exam" now comes first, and paste is labeled for what it is.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Projekt-Assistent: „Klausur erfassen“ übernimmt eingegebene Inhalte jetzt automatisch — die Klausur-Aufgabe geht nicht mehr verloren, wenn „Übernehmen“ übersprungen wurde.',
      en: 'Project wizard: "Enter exam" now saves entered content automatically — the exam task is no longer lost when "Apply" was skipped.',
    },
  },
  {
    date: '2026-08-31',
    audience: 'benger',
    text: {
      de: 'Organisationsverwaltung: Eine geänderte Beschreibung ist sofort sichtbar, ohne die Seite neu zu laden.',
      en: 'Organization management: an edited description now shows immediately, without reloading the page.',
    },
  },
  {
    date: '2026-08-25',
    audience: 'benger',
    text: {
      de: 'AI-Bewertungsbogen ist jetzt ein eigener Schritt im Projekt-Assistenten (experimentell) und funktioniert für jede Klausur, nicht nur KI-generierte.',
      en: 'The AI grading rubric is now its own project-wizard step (experimental) and works for any exam, not just AI-generated ones.',
    },
  },
  {
    date: '2026-08-25',
    audience: 'both',
    text: {
      de: 'Alle Nutzer:innen können jetzt über das Kontomenü zwischen Studierenden- und Expertenansicht wechseln.',
      en: 'Everyone can now switch between the student and expert interface from the account menu.',
    },
  },
  {
    date: '2026-08-25',
    audience: 'benger',
    text: {
      de: 'Projekttyp (Klausur / Kartenstapel) ist jetzt in den Projektdetails änderbar und steuert die Sichtbarkeit für Studierende.',
      en: 'The project type (exam / flashcard deck) is now editable in the project details and controls student visibility.',
    },
  },
  {
    date: '2026-08-24',
    audience: 'both',
    text: {
      de: 'Neue Changelog-Seite: alle Neuerungen im Überblick, erreichbar über den Footer.',
      en: "New changelog page: an overview of what's new, reachable from the footer.",
    },
  },
]
