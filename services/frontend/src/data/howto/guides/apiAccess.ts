import type { HowToGuide } from '@/lib/howto'

export const API_ACCESS_GUIDES: HowToGuide[] = [
  {
    id: 'api-zugaenge',
    category: 'integrations',
    title: {
      de: 'Wie richte ich einen API-Zugang für Skripte oder einen Benchmark-Runner ein?',
      en: 'How do I set up API access for scripts or a benchmark runner?',
    },
    summary: {
      de: 'Mit einem **Zugangsschlüssel** (beginnt mit `bgr_`). Schlüssel für deine Organisation legst du als Org- oder Gruppen-Admin unter **API-Zugänge** an, persönliche Schlüssel in deinem [Profil](/profile). Der Schlüssel wird dir nur einmal angezeigt.',
      en: 'With an **access key** (it starts with `bgr_`). As an org or group admin you create keys for your organization under **API access**, personal keys on your [profile](/profile). The key is shown to you only once.',
    },
    steps: {
      de: [
        '**Schlüssel anlegen**: Für die Organisation öffnest du [Benutzer & Organisationen](/users-organizations), wählst die Organisation und klickst auf **API-Zugänge**. Für dich selbst gehst du in dein [Profil](/profile) zu **API-Zugänge**. Dort klickst du auf **Neuer Schlüssel** und gibst ihm einen Namen, an dem du ihn später wiedererkennst.',
        '**Umfang wählen**: Wähle eine Voreinstellung: **Benchmark nur lesen**, **Benchmark ausführen und einreichen** oder **Vollzugriff auf die eigene Organisation**. Unter **Erweitert** siehst du jede Berechtigung einzeln. Bei Organisationsschlüsseln wählst du dazu die Rolle, bei Bedarf eine Gruppe und einzelne Projekte. Die Gültigkeit steht auf einem Jahr.',
        '**Kopieren**: Nach **Schlüssel anlegen** erscheint der vollständige Schlüssel. Kopiere ihn sofort mit **Kopieren** und bewahre ihn sicher auf, zum Beispiel in einem Passwortmanager. Danach siehst du nur noch die Kennung.',
        '**Verbindung testen**: Klicke auf **Verbindung testen**. BenGER ruft damit die Schnittstelle so auf, wie es dein Skript tun wird, und zeigt dir Organisation und Berechtigungen des Schlüssels.',
        '**In Skript oder Runner einsetzen**: Übernimm das angezeigte `curl`- oder Python-Beispiel. Der Schlüssel steht im Header `Authorization: Bearer <Schlüssel>`. Lege ihn als Umgebungsvariable oder Geheimnis deines Runners ab, nie im Quelltext.',
      ],
      en: [
        '**Create the key**: for the organization, open [Users & organizations](/users-organizations), pick the organization and click **API access**. For yourself, go to **API access** on your [profile](/profile). Click **New key** and give it a name you will recognize later.',
        '**Choose the scope**: pick a preset: **Read the benchmark only**, **Run and submit to the benchmark** or **Full access to your own organization**. **Advanced** lists every permission on its own. For organization keys you also choose the role and, if needed, a group and single projects. Validity defaults to one year.',
        '**Copy**: after **Create key** the full key appears. Copy it right away with **Copy** and keep it safe, for example in a password manager. Afterwards you only see its identifier.',
        "**Test the connection**: click **Test connection**. BenGER calls the API the way your script will and shows the key's organization and permissions.",
        '**Use it in a script or runner**: take the `curl` or Python example shown. The key goes into the `Authorization: Bearer <key>` header. Store it as an environment variable or a secret of your runner, never in the source code.',
      ],
    },
    tips: {
      de: [
        '**Erneuern** legt einen neuen Schlüssel mit denselben Einstellungen an. Der alte funktioniert weiter, bis du ihn widerrufst. So stellst du deine Skripte ohne Ausfall um.',
        'Unter **Nutzung** siehst du, wie oft ein Schlüssel in den letzten 30 Tagen verwendet wurde und welche Schnittstellen er aufgerufen hat.',
        'Ein Organisationsschlüssel handelt als eigenes Dienstkonto. Ein persönlicher Schlüssel handelt als du und sieht nie mehr als du selbst.',
      ],
      en: [
        '**Renew** creates a new key with the same settings. The old one keeps working until you revoke it, so your scripts switch over without downtime.',
        '**Usage** shows how often a key was used in the last 30 days and which endpoints it called.',
        'An organization key acts as its own service account. A personal key acts as you and never sees more than you do.',
      ],
    },
    pitfalls: {
      de: [
        'Den vollständigen Schlüssel siehst du nur direkt nach dem Anlegen. Hast du ihn verloren, lege einen neuen an und widerrufe den alten.',
        'Musterlösungen kann ein Organisationsschlüssel nur mit der Rolle **Mitwirkender** lesen.',
        'Ist ein Schlüssel in falsche Hände geraten, widerrufe ihn sofort mit **Widerrufen**. Er funktioniert dann nicht mehr.',
      ],
      en: [
        'You only see the full key right after creating it. If you lost it, create a new one and revoke the old one.',
        'An organization key can read reference solutions only with the **Contributor** role.',
        'If a key got into the wrong hands, revoke it at once with **Revoke**. It stops working immediately.',
      ],
    },
    links: [
      {
        label: { de: 'Profil', en: 'Profile' },
        href: '/profile',
      },
      {
        label: {
          de: 'Benutzer & Organisationen',
          en: 'Users & organizations',
        },
        href: '/users-organizations',
      },
    ],
    keywords: {
      de: [
        'API',
        'API-Zugang',
        'Zugangsschlüssel',
        'Token',
        'Schnittstelle',
        'Skript',
        'Runner',
        'Benchmark',
        'bgr_',
        'curl',
        'Python',
      ],
      en: [
        'api',
        'api access',
        'access key',
        'token',
        'script',
        'runner',
        'benchmark',
        'bgr_',
        'curl',
        'python',
      ],
    },
  },
]
