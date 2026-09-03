/**
 * /architecture page content — the platform's technical architecture as of
 * 2026-09, bilingual inline (like changelog and how-to guides) so the page
 * stays reviewable in one file. Keep it truthful: every bullet describes
 * something that exists in the repos today, not a roadmap.
 */

export type ArchBilingual = { de: string; en: string }

export interface ArchSection {
  id: string
  title: ArchBilingual
  /** Lead paragraph. Inline **bold** and `code` are rendered. */
  intro: ArchBilingual
  bullets: { de: string[]; en: string[] }
  /** Optional monospace diagram (language-neutral). */
  diagram?: string
}

export const ARCHITECTURE_DIAGRAM = `    +----------------------------------------------------+
    |                 Traefik (Ingress)                  |
    |what-a-benger.net / vertretbar.net / org subdomains |
    +----------------------------------------------------+
                |                             |
+-----------------------+       +-----------------------+
|        Frontend       |       |          API          |
|  Next.js 15, React 18 |  -->  |  FastAPI, Pydantic v2 |
| expert + student shell|       | sync + async DB lanes |
|      slot system      |       | JWT, org context, LTI |
+-----------------------+       +-----------------------+
                                    |       |       |
+-----------------------------------+       |       +-----------------+
v                                           v                         v
+-----------------------+   Redis   +-----------------------+   +-----------------------+
|      Worker pools     |<- broker ->|       PostgreSQL      |   |       MinIO / S3      |
|    Celery, 6 queues   |   pub/sub  |     Alembic, JSONB    |   |     import/export,    |
|    + beat schedule    |            |                       |   |        uploads        |
+-----------------------+            +-----------------------+   +-----------------------+

benger-platform (open core, Apache-2.0) + benger-extended (private): one image set;
extended plugs into API hooks, frontend slots and worker metric mappings.`

export const ARCHITECTURE_SECTIONS: ArchSection[] = [
  {
    id: 'overview',
    title: { de: 'Überblick: Open Core, zwei Oberflächen, ein System', en: 'Overview: open core, two interfaces, one system' },
    intro: {
      de: 'BenGER ist als **Open-Core-System** gebaut. Das öffentliche Repository `benger-platform` (Apache-2.0) enthält Annotationssystem, Generierung, Evaluation, Berichte und Organisationsverwaltung. Das private Paket `benger-extended` liefert die proprietären Erweiterungen (Klausurlösung, KI-Korrektur, Korrektur- und Review-Workflows, Timer, Bestenlisten für Menschen, LTI, die Studierendenplattform Vertretbar) und wird beim Build in dieselben Images eingebettet. In Produktion läuft ein Satz Container, der beide Oberflächen bedient: die Expertenplattform auf what-a-benger.net und Vertretbar auf vertretbar.net.',
      en: 'BenGER is built as an **open-core system**. The public repository `benger-platform` (Apache-2.0) contains the annotation system, generation, evaluation, reports and organization management. The private package `benger-extended` supplies the proprietary extensions (exam solving, AI grading, grading and review workflows, timers, human leaderboards, LTI, the student platform Vertretbar) and is embedded into the same images at build time. Production runs one set of containers serving both interfaces: the expert platform on what-a-benger.net and Vertretbar on vertretbar.net.',
    },
    bullets: {
      de: [
        'Eine Datenbank, ein Konto: Die Oberfläche wird pro Host und Nutzer:in entschieden (Studierenden- oder Expertenansicht), nicht pro Deployment.',
        'Die Community-Edition (nur `benger-platform`) läuft ohne die Erweiterungen: Slots und Registries bleiben leer, die Kernfunktionen funktionieren unverändert.',
        'Datenbankschema und Migrationen für alle Funktionen, auch die erweiterten, liegen im Platform-Repository. Die Erweiterungen bringen Logik mit, kein zweites Migrationssystem.',
      ],
      en: [
        'One database, one account: the interface is decided per host and user (student or expert view), not per deployment.',
        'The community edition (`benger-platform` alone) runs without the extensions: slots and registries stay empty, the core functions work unchanged.',
        'Database schema and migrations for every feature, including the extended ones, live in the platform repository. The extensions bring logic, not a second migration system.',
      ],
    },
    diagram: ARCHITECTURE_DIAGRAM,
  },
  {
    id: 'frontend',
    title: { de: 'Frontend', en: 'Frontend' },
    intro: {
      de: '**Next.js 15** (App Router, Turbopack) mit React 18, TypeScript und Tailwind CSS. Das Frontend ist eine Anwendung mit zwei Shells: der Experten-Shell mit Seitenleiste und Konfigurationskarten und der Studierenden-Shell mit Lernstatistik, Klausuren und Karteikarten. Welche Shell rendert, entscheidet der Host (vertretbar.net ist auf die Studierenden-Shell festgelegt) zusammen mit der gespeicherten Nutzerpräferenz.',
      en: '**Next.js 15** (App Router, Turbopack) with React 18, TypeScript and Tailwind CSS. The frontend is one application with two shells: the expert shell with sidebar and configuration cards, and the student shell with learning statistics, exams and flashcards. Which shell renders is decided by the host (vertretbar.net is locked to the student shell) together with the stored user preference.',
    },
    bullets: {
      de: [
        'Erweiterungspunkte: ein Slot-System (`registerSlot`/`useSlot`) für ganze Seiten und Karten, Registries für Metriken, Metrik-Editoren und Zellen-Renderer, Wizard-Vorlagen, Projekttyp-Presets, Post-Create-Hooks, Changelog- und Anleitungs-Einträge.',
        'Zwei Sprachen (Deutsch, Englisch) über eine zentrale Übersetzungsschicht; Dark Mode; responsive Layouts.',
        'Echtzeit: Server-Sent Events für Benachrichtigungen und Evaluationsfortschritt, WebSockets für laufende Generierungen.',
        'Der Next-Server proxyt API-Aufrufe und setzt Sitzungs-Cookies pro Basisdomain, sodass Organisations-Subdomains die Sitzung teilen.',
      ],
      en: [
        'Extension points: a slot system (`registerSlot`/`useSlot`) for whole pages and cards, registries for metrics, metric editors and cell renderers, wizard templates, project-type presets, post-create hooks, changelog and guide entries.',
        'Two languages (German, English) through one translation layer; dark mode; responsive layouts.',
        'Real time: Server-Sent Events for notifications and evaluation progress, WebSockets for running generations.',
        'The Next server proxies API calls and sets session cookies per base domain, so organization subdomains share the session.',
      ],
    },
  },
  {
    id: 'api',
    title: { de: 'API', en: 'API' },
    intro: {
      de: '**FastAPI** mit Pydantic v2 und SQLAlchemy 2. Die API kennt zwei Datenbank-Lanes gegen dieselbe PostgreSQL-Instanz: die synchrone (psycopg2) für bestehenden Code und die asynchrone (asyncpg), in die neue Handler geschrieben werden. Authentifizierung über JWT mit Refresh-Tokens, der Organisationskontext kommt aus der Subdomain.',
      en: '**FastAPI** with Pydantic v2 and SQLAlchemy 2. The API has two database lanes against the same PostgreSQL instance: the synchronous one (psycopg2) for existing code and the asynchronous one (asyncpg) that new handlers are written against. Authentication via JWT with refresh tokens; the organization context comes from the subdomain.',
    },
    bullets: {
      de: [
        'Rund 36 Router-Module: Projekte und Aufgaben, Import/Export, Generierung, Evaluation und Sofort-Evaluation, Organisationen mit Gruppen und Einladungen, API-Schlüssel (persönlich, Organisation, Gruppe), eigene Modelle, Prompt-Strukturen, Bestenlisten, Berichte, Läufe, Benachrichtigungen, Objektspeicher, LTI-Administration, Feature-Flags, Health.',
        'Alembic-Migrationen laufen beim Start unter einem Advisory-Lock; ein Schema-Validator prüft danach Modell und Datenbank gegeneinander.',
        'Der Modellkatalog (`llm_models.yaml`) ist die einzige Quelle für Modelle, Preise und Parameter-Constraints und wird beim Start in die Datenbank geseedet.',
        'Die Erweiterungen laden über `extensions.py`: zusätzliche Router und Lifecycle-Hooks (nach Annotation, nach Entwurf, nach Speichern einer Evaluationskonfiguration, bei Registrierung) mit einem Versions-Handshake zwischen Kern und Erweiterung.',
        '`/health` prüft Postgres und Redis (Pflicht) sowie die Worker (weich); Drittanbieter werden bewusst nicht in der Liveness-Probe abgefragt.',
      ],
      en: [
        'Around 36 router modules: projects and tasks, import/export, generation, evaluation and immediate evaluation, organizations with groups and invitations, API keys (personal, organization, group), custom models, prompt structures, leaderboards, reports, runs, notifications, object storage, LTI administration, feature flags, health.',
        'Alembic migrations run at startup under an advisory lock; a schema validator then checks models against the database.',
        'The model catalog (`llm_models.yaml`) is the single source for models, prices and parameter constraints and is seeded into the database at startup.',
        'Extensions load through `extensions.py`: additional routers and lifecycle hooks (after annotation, after draft, after saving an evaluation config, on signup) with a version handshake between core and extension.',
        '`/health` checks Postgres and Redis (required) and the workers (soft); third-party providers are deliberately not part of the liveness probe.',
      ],
    },
  },
  {
    id: 'workers',
    title: { de: 'Worker und Warteschlangen', en: 'Workers and queues' },
    intro: {
      de: '**Celery** verarbeitet alles, was länger dauert. Statt eines Workers für alles gibt es sechs getrennte Warteschlangen, die von eigenen Worker-Pools bedient werden: `interactive` (Sofort-Evaluation, Entwürfe), `emails`, `maintenance`, `generation`, `evaluation` und `bulk` (Import/Export). So kann eine große Batch-Evaluation die KI-Korrektur einer einzelnen Abgabe nicht blockieren.',
      en: '**Celery** handles everything that takes longer. Instead of one worker for everything there are six separate queues served by their own worker pools: `interactive` (immediate evaluation, drafts), `emails`, `maintenance`, `generation`, `evaluation` and `bulk` (import/export). A large batch evaluation therefore cannot block the AI grading of a single submission.',
    },
    bullets: {
      de: [
        'Generierung: Prompt-Strukturen mit `$feld`-Referenzen und Vorlagen, Schutz vor Antwort-Leaks (Referenzfelder werden nie in Prompts eingesetzt), Mehrfachläufe pro Aufgabe, Provider-Adapter für OpenAI, Anthropic, Google, DeepInfra, Grok, Mistral, Cohere und OpenAI-kompatible eigene Endpunkte.',
        'Evaluation: lexikalische, semantische und Klassifikationsmetriken, LLM-Judges (klassisch, benutzerdefiniert, Falllösung mit Notenpunkten, Bewertungsbogen), Ensembles mit Inter-Judge-Agreement, statistische Auswertung.',
        'Beat-Zeitplan: stündlich Aggregat- und Bestenlisten-Neuberechnung, halbstündlich die Nachholung fehlender Sofort-Evaluationen, nächtliche Datenbanksicherung als Kubernetes-CronJob.',
        'Import und Export laufen ausschließlich über den Objektspeicher: die API nimmt keine großen Dateien entgegen, Clients laden direkt per vorsignierter URL hoch und herunter.',
      ],
      en: [
        'Generation: prompt structures with `$field` references and templates, protection against answer leaks (reference fields are never inserted into prompts), multiple runs per task, provider adapters for OpenAI, Anthropic, Google, DeepInfra, Grok, Mistral, Cohere and OpenAI-compatible custom endpoints.',
        'Evaluation: lexical, semantic and classification metrics, LLM judges (classic, custom, case solution with grade points, grading sheet), ensembles with inter-judge agreement, statistical analysis.',
        'Beat schedule: hourly aggregate and leaderboard recomputation, half-hourly catch-up of missing immediate evaluations, nightly database backup as a Kubernetes CronJob.',
        'Import and export run exclusively through object storage: the API accepts no large files, clients upload and download directly via presigned URLs.',
      ],
    },
  },
  {
    id: 'storage',
    title: { de: 'Datenhaltung', en: 'Data storage' },
    intro: {
      de: 'Drei Speicher, jeder mit klarer Aufgabe: **PostgreSQL** für alle Anwendungsdaten, **Redis** für Warteschlangen und Echtzeit, **MinIO** (S3-kompatibel) für Dateien.',
      en: 'Three stores, each with a clear job: **PostgreSQL** for all application data, **Redis** for queues and real time, **MinIO** (S3-compatible) for files.',
    },
    bullets: {
      de: [
        'PostgreSQL: Nutzer:innen, Organisationen und Gruppen, Projekte, Aufgaben, Annotationen, Generierungen, Evaluationen, Lernverläufe. Konfigurationen liegen als JSONB und werden serverseitig tief zusammengeführt, damit parallele Speichervorgänge sich nicht überschreiben.',
        'Redis: Celery-Broker, Pub/Sub für Benachrichtigungen und Fortschritt, Rate-Limits, Sitzungs-Cache.',
        'MinIO: Projekt-Import und -Export, Datei-Uploads, Organisations-Speicherverbindungen für Cloud-Importe. Der Objektspeicher ist eine harte Abhängigkeit in beiden Editionen; ohne ihn startet die API nicht.',
      ],
      en: [
        'PostgreSQL: users, organizations and groups, projects, tasks, annotations, generations, evaluations, learning histories. Configurations are stored as JSONB and deep-merged server-side so parallel saves do not overwrite each other.',
        'Redis: Celery broker, pub/sub for notifications and progress, rate limits, session cache.',
        'MinIO: project import and export, file uploads, organization storage connections for cloud imports. Object storage is a hard dependency in both editions; without it the API does not start.',
      ],
    },
  },
  {
    id: 'annotation',
    title: { de: 'Annotationssystem', en: 'Annotation system' },
    intro: {
      de: 'Ein eigenes, **Label-Studio-kompatibles** Annotationssystem ohne externen Dienst. Die Oberfläche wird aus einer XML-Konfiguration gerendert (`View`, `Text`, `TextArea`, `Choices`, `Labels`, `Rating`, `Likert`, `Number`, `Image`); die Erweiterungen registrieren zusätzliche Komponenten für die Klausurlösung (`Angabe`, `Notizen`, `Gliederung`, `Loesung`).',
      en: 'A native, **Label-Studio-compatible** annotation system with no external service. The interface is rendered from an XML configuration (`View`, `Text`, `TextArea`, `Choices`, `Labels`, `Rating`, `Likert`, `Number`, `Image`); the extensions register additional components for exam solving (`Angabe`, `Notizen`, `Gliederung`, `Loesung`).',
    },
    bullets: {
      de: [
        'Zuweisungsmodi (offen, manuell, automatisch), Limits pro Aufgabe, zufällige Reihenfolge, Zeitlimits mit striktem Timer, Zugriffsfenster, Entwürfe mit wiederherstellbaren Zwischenständen.',
        'Sofort-Evaluation nach jeder Abgabe über einen serverseitigen Hook, der jede Abgabe genau einmal bewertet, auch wenn der Browser den Aufruf nie abgesetzt hat.',
        'Review-Phase und menschliche Korrektur (Falllösung, eigene Rubrik, Kommentare) als Erweiterung; Blinding der Referenzfelder bis zur Abgabe.',
        'Exporte als JSON, CSV, TSV, TXT, Label-Studio-Format, NDJSON und Anki; Round-Trip-Import ganzer Projekte samt Annotationen und Bewertungen.',
      ],
      en: [
        'Assignment modes (open, manual, automatic), per-task limits, random order, time limits with a strict timer, access windows, drafts with restorable checkpoints.',
        'Immediate evaluation after every submission through a server-side hook that grades each submission exactly once, even when the browser never issued the call.',
        'Review phase and human grading (case solution, custom rubric, comments) as an extension; blinding of reference fields until submission.',
        'Exports as JSON, CSV, TSV, TXT, Label Studio format, NDJSON and Anki; round-trip import of whole projects including annotations and evaluations.',
      ],
    },
  },
  {
    id: 'organizations',
    title: { de: 'Organisationen, Gruppen und Zugriff', en: 'Organizations, groups and access' },
    intro: {
      de: 'Nutzer:innen können mehreren **Organisationen** angehören; jede Organisation hat eine eigene Subdomain (`{slug}.what-a-benger.net`) und die Rollen Admin, Mitwirkender und Annotator. **Gruppen** (z.B. Lehrstühle) teilen eine Organisation weiter auf: Projektzuordnungen und API-Schlüssel können auf eine Gruppe beschränkt werden, Gruppen-Admins verwalten ihre Gruppe ohne organisationsweite Rechte.',
      en: 'Users can belong to several **organizations**; each organization has its own subdomain (`{slug}.what-a-benger.net`) and the roles admin, contributor and annotator. **Groups** (e.g. chairs) split an organization further: project attachments and API keys can be restricted to a group, and group admins manage their group without organization-wide rights.',
    },
    bullets: {
      de: [
        'Sichtbarkeit von Projekten: privat, Organisation (optional eine Gruppe) oder öffentlich; zusätzlich Freigabe-Links mit Passwort und ein Verzeichnis (*Entdecken*) für Studierende. Wer über Link oder Verzeichnis beitritt, bekommt die schmale Teilnehmer-Stufe ohne Referenzdaten.',
        'API-Schlüssel werden verschlüsselt gespeichert. Auflösung pro Aufruf: Stellt die Organisation Schlüssel bereit, zahlt sie (Gruppenschlüssel vor Organisationsschlüssel), sonst der persönliche Schlüssel. Eigene Modelle (BYOM) nutzen immer den Schlüssel der aufrufenden Person.',
        'Einladungen per E-Mail mit siebentägigem Token, optional gruppenbezogen; Benachrichtigungen in der App und per E-Mail (SendGrid) mit Ruhezeiten und Digest.',
        'Feature-Flags (datenbankgestützt, von Superadmins geschaltet) blenden ganze Bereiche ein oder aus.',
      ],
      en: [
        'Project visibility: private, organization (optionally one group) or public; plus password-protected share links and a directory (*Discover*) for students. Whoever joins via link or directory gets the narrow participant tier without reference data.',
        'API keys are stored encrypted. Resolution per call: if the organization provides keys it pays (group key before organization key), otherwise the personal key. Custom models (BYOM) always use the calling user’s key.',
        'Invitations by email with a seven-day token, optionally group-scoped; notifications in-app and by email (SendGrid) with quiet hours and digests.',
        'Feature flags (database-backed, switched by superadmins) show or hide whole sections.',
      ],
    },
  },
  {
    id: 'integrations',
    title: { de: 'Integrationen', en: 'Integrations' },
    intro: {
      de: '**LTI 1.3** verbindet BenGER mit Moodle und ILIAS: Dynamic Registration über einen einmaligen Einladungslink, Just-in-time-Anlage von Konten beim ersten Start, einmalige Einwilligung, Verknüpfung einer Aktivität mit einer Klausur und Rückgabe der Noten (0 bis 18 Notenpunkte) über den Assignment and Grade Service.',
      en: '**LTI 1.3** connects BenGER with Moodle and ILIAS: dynamic registration through a one-time invitation link, just-in-time account creation on first launch, one-time consent, linking an activity to an exam and grade passback (0 to 18 grade points) via the Assignment and Grade Service.',
    },
    bullets: {
      de: [
        'KI-Anbieter: OpenAI, Anthropic, Google, DeepInfra (Llama, Qwen, DeepSeek, GLM, Kimi u.a.), Grok, Mistral, Cohere. Eigene OpenAI-kompatible Endpunkte lassen sich registrieren und teilen; eine SSRF-Sperre verhindert Aufrufe ins interne Netz.',
        'E-Mail über SendGrid, mit Marken-Absender je Host (BenGER oder Vertretbar).',
        'Cloud-Speicherverbindungen von Organisationen (S3) für Importe direkt aus dem eigenen Bucket.',
      ],
      en: [
        'AI providers: OpenAI, Anthropic, Google, DeepInfra (Llama, Qwen, DeepSeek, GLM, Kimi and more), Grok, Mistral, Cohere. Custom OpenAI-compatible endpoints can be registered and shared; an SSRF guard blocks calls into internal networks.',
        'Email via SendGrid, with a branded sender per host (BenGER or Vertretbar).',
        'Organization cloud storage connections (S3) for imports straight from your own bucket.',
      ],
    },
  },
  {
    id: 'deployment',
    title: { de: 'Betrieb, Deployment und CI', en: 'Operations, deployment and CI' },
    intro: {
      de: 'Produktion läuft auf **Kubernetes (K3s)** mit Helm, in zwei Namespaces: `benger` (Produktion) und `benger-staging`. Traefik terminiert TLS mit Wildcard-Zertifikaten für what-a-benger.net und vertretbar.net und leitet Organisations-Subdomains an dieselbe Frontend-Instanz.',
      en: 'Production runs on **Kubernetes (K3s)** with Helm, in two namespaces: `benger` (production) and `benger-staging`. Traefik terminates TLS with wildcard certificates for what-a-benger.net and vertretbar.net and routes organization subdomains to the same frontend instance.',
    },
    bullets: {
      de: [
        'Deployments: API und Frontend mit je zwei Replikas und Rolling Updates, Worker-Pools pro Warteschlange, Celery Beat, MinIO, PostgreSQL, Redis, ein Migrations-Job vor jedem Rollout und ein nächtlicher Backup-CronJob. Autoscaling ist vorbereitet, aber ausgeschaltet.',
        'CI/CD: Pull Requests auf das Platform-Repository laufen Jest und Lint; ein Merge auf `main` läuft zusätzlich die vollständigen API- und Worker-Suiten (sechs parallele Shards) und löst danach den Build im Extended-Repository aus, der die Images nach GHCR pusht und Produktion ausrollt. Pull Requests im Extended-Repository deployen nach Staging.',
        'Nächtliche Läufe: kompletter Test-Suite-Lauf inklusive End-to-End-Tests, Coverage-Ratchets und Mutation-Testing; ein Drift-Check vergleicht den Modellkatalog mit der Datenbank.',
        'Lokale Entwicklung mit Docker Compose und Traefik unter `benger.localhost` und `vertretbar.localhost`, Hot Reload über Turbopack, isolierte Test-Infrastruktur (PostgreSQL 5433, Redis 6380, eigener MinIO).',
      ],
      en: [
        'Deployments: API and frontend with two replicas each and rolling updates, worker pools per queue, Celery beat, MinIO, PostgreSQL, Redis, a migration job before every rollout and a nightly backup CronJob. Autoscaling is prepared but switched off.',
        'CI/CD: pull requests on the platform repository run Jest and lint; a merge to `main` additionally runs the full API and worker suites (six parallel shards) and then triggers the build in the extended repository, which pushes the images to GHCR and rolls out production. Pull requests in the extended repository deploy to staging.',
        'Nightly runs: the complete test suite including end-to-end tests, coverage ratchets and mutation testing; a drift check compares the model catalog with the database.',
        'Local development with Docker Compose and Traefik under `benger.localhost` and `vertretbar.localhost`, hot reload via Turbopack, isolated test infrastructure (PostgreSQL 5433, Redis 6380, its own MinIO).',
      ],
    },
  },
]
