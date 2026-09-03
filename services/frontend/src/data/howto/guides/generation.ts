import type { HowToGuide } from '@/lib/howto'

export const GENERATION_GUIDES: HowToGuide[] = [
  {
    id: 'generation-run',
    category: 'generation',
    title: { de: 'Wie lasse ich KI-Modelle Antworten generieren?', en: 'How do I have AI models generate answers?' },
    summary: {
      de: 'Auf der Projektseite unter **Generierungskonfiguration** Modelle auswählen und einen Prompt anlegen, dann **Generierung starten**. Im Dialog wählen Sie Modus (*Nur fehlende generieren* oder *Alle generieren*), Modelle, Prompt-Strukturen und Parameter. Den Fortschritt sehen Sie unter [Generierung](/generations) als Matrix Aufgabe × Modell.',
      en: 'On the project page under **Generation configuration** pick models and create a prompt, then **Start generation**. In the dialog choose the mode (*Generate missing only* or *Generate all*), models, prompt structures and parameters. Progress is shown under [Generation](/generations) as a task × model matrix.',
    },
    steps: {
      de: [
        '**Modellauswahl**: Modelle aus dem Katalog ankreuzen. Es erscheinen nur Anbieter, für die ein Schlüssel vorliegt. Pro Modell lassen sich Token-Limit und Denkbudget (Reasoning) setzen.',
        '**Prompt-Strukturen**: System-Prompt (Rolle) und Instruktions-Prompt (Aufgabe). Felder der Aufgabe fügen Sie als `$feld` ein, z.B. `Sachverhalt:\n$sachverhalt`. Mehrere Strukturen sind möglich, aktive Strukturen laufen alle.',
        '**Generierung starten**: Modus wählen, Modelle und Strukturen bestätigen, unter *Erweiterte Einstellungen* Läufe pro Aufgabe, Temperatur, Max. Tokens und Seed. Die **Kostenschätzung** rechnet Aufgaben × Läufe × Modelle.',
        'Fortschritt und Ergebnisse: [Generierung](/generations). Klick auf eine Zelle zeigt die Antwort, den verwendeten Prompt und die Parameter. Rechtsklick: *Generieren* oder *Neu generieren*. Alle Läufe mit Status: [Läufe](/runs).',
      ],
      en: [
        '**Model selection**: tick models from the catalog. Only providers with a key appear. Per model you can set the token limit and thinking budget (reasoning).',
        '**Prompt structures**: system prompt (role) and instruction prompt (task). Insert task fields as `$field`, e.g. `Case facts:\n$sachverhalt`. Several structures are possible, all active ones run.',
        '**Start generation**: choose the mode, confirm models and structures, under *Advanced settings* runs per task, temperature, max tokens and seed. The **cost estimate** computes tasks × runs × models.',
        'Progress and results: [Generation](/generations). Clicking a cell shows the answer, the prompt used and the parameters. Right-click: *Generate* or *Regenerate*. All runs with status: [Runs](/runs).',
      ],
    },
    tips: {
      de: [
        'Referenzfelder wie `musterloesung`, `answer`, `solution`, `ground_truth` oder `annotations` werden nie in Prompts eingesetzt. So kann das Modell die Lösung nicht sehen.',
        'Modelle der GPT-5- und o-Reihe erzwingen Temperatur 1.0, der Regler wird für sie ignoriert. Anthropic und Google unterstützen keinen Seed.',
        '*Nur fehlende generieren* überspringt Aufgaben, deren Antwort mit unverändertem Prompt schon existiert. Nach einer Prompt-Änderung werden sie neu erzeugt.',
        'Für Studien mit mehreren Durchläufen setzen Sie *Läufe pro Aufgabe* größer als 1. Jeder Lauf wird einzeln gespeichert und ausgewertet.',
      ],
      en: [
        'Reference fields such as `musterloesung`, `answer`, `solution`, `ground_truth` or `annotations` are never inserted into prompts, so the model cannot see the solution.',
        'GPT-5 and o-series models enforce temperature 1.0, the slider is ignored for them. Anthropic and Google do not support a seed.',
        '*Generate missing only* skips tasks whose answer already exists with an unchanged prompt. After a prompt change they are regenerated.',
        'For studies with several passes set *Runs per task* above 1. Every run is stored and evaluated separately.',
      ],
    },
    links: [
      { label: { de: 'Generierung', en: 'Generation' }, href: '/generations' },
      { label: { de: 'Modellkatalog', en: 'Model catalog' }, href: '/models' },
    ],
    keywords: { de: ['Generierung', 'generieren', 'Prompt', 'System-Prompt', 'Instruktion', 'Platzhalter', 'Temperatur', 'Seed', 'Läufe pro Aufgabe', 'Kostenschätzung', 'Modellauswahl'], en: ['generation', 'generate', 'prompt', 'system prompt', 'instruction', 'placeholder', 'temperature', 'seed', 'runs per task', 'cost estimate', 'model selection'] },
  },
  {
    id: 'model-catalog',
    category: 'generation',
    title: { de: 'Welche Modelle gibt es und was kosten sie?', en: 'Which models are available and what do they cost?' },
    summary: {
      de: 'Der [Modellkatalog](/models) listet alle Modelle mit Anbieter, Fähigkeiten, Preisen pro Million Tokens und Empfehlungen für Generierung und Bewertung: OpenAI, Anthropic, Google, DeepInfra (Llama, Qwen, DeepSeek, GLM, Kimi u.a.), Grok, Mistral und Cohere. Die Kosten fallen beim Anbieter über den genutzten Schlüssel an, nicht bei BenGER.',
      en: 'The [model catalog](/models) lists every model with provider, capabilities, prices per million tokens and recommendations for generation and evaluation: OpenAI, Anthropic, Google, DeepInfra (Llama, Qwen, DeepSeek, GLM, Kimi and more), Grok, Mistral and Cohere. Costs are charged by the provider via the key used, not by BenGER.',
    },
    tips: {
      de: [
        'Die *Kostenschätzung* im Generierungs- und Evaluationsdialog nutzt genau diese Preise.',
        'Katalogänderungen sind unter [Änderungen](/changelog) nachzulesen. Abgekündigte Modelle bleiben in alten Ergebnissen sichtbar, sind aber nicht mehr wählbar.',
      ],
      en: [
        'The *cost estimate* in the generation and evaluation dialogs uses exactly these prices.',
        'Catalog changes are listed under [Changelog](/changelog). Retired models stay visible in old results but can no longer be selected.',
      ],
    },
    keywords: { de: ['Modellkatalog', 'Modelle', 'Preise', 'Kosten', 'Token', 'Anbieter', 'GPT', 'Claude', 'Gemini', 'Llama'], en: ['model catalog', 'models', 'prices', 'cost', 'tokens', 'providers'] },
  },
  {
    id: 'api-keys',
    category: 'generation',
    title: { de: 'Wie richte ich einen API-Schlüssel ein und wessen Schlüssel wird benutzt?', en: 'How do I set up an API key and whose key gets used?' },
    summary: {
      de: 'KI-Modelle brauchen einen Schlüssel des jeweiligen Anbieters. Entweder hinterlegen Sie Ihren eigenen unter [Profil](/profile) → **API-Schlüssel-Verwaltung**, oder Ihre Organisation stellt Schlüssel bereit. Die Regel: Stellt die Organisation Schlüssel bereit, zahlt sie für ihre Projekte, sonst zahlt der eigene Schlüssel.',
      en: 'AI models need a key of the respective provider. Either store your own under [Profile](/profile) → **API key management**, or your organization provides keys. The rule: if the organization provides keys, it pays for its projects, otherwise your own key pays.',
    },
    steps: {
      de: [
        '**Eigener Schlüssel**: [Profil](/profile) → *API-Schlüssel-Verwaltung* → Anbieter wählen (OpenAI, Anthropic, Google, DeepInfra, Grok/xAI, Mistral, Cohere) → Schlüssel einfügen → *Testen* → *Speichern*. Der Schlüssel wird verschlüsselt gespeichert und nie angezeigt.',
        '**Schlüssel der Organisation** (Admin): [Benutzer & Organisationen](/users-organizations) → Organisation → **API-Schlüssel** → Schalter **Organisation stellt API-Schlüssel bereit** einschalten und je Anbieter einen Schlüssel hinterlegen. Optional den **Geltungsbereich** auf eine Gruppe setzen.',
        '**Wer zahlt**: Die Karte **Abrechnung** auf jeder Projektseite sagt es Ihnen. *Organisation übernimmt die Kosten*, wenn die Organisation Schlüssel bereitstellt; sonst *läuft über den eigenen API-Schlüssel*.',
        'Bei Gruppenprojekten wird zuerst der Gruppenschlüssel genutzt, dann der Organisationsschlüssel. Nie der Schlüssel einer anderen Gruppe.',
      ],
      en: [
        '**Your own key**: [Profile](/profile) → *API key management* → pick the provider (OpenAI, Anthropic, Google, DeepInfra, Grok/xAI, Mistral, Cohere) → paste the key → *Test* → *Save*. The key is stored encrypted and never shown again.',
        '**Organization keys** (admin): [Users & organizations](/users-organizations) → organization → **API keys** → switch on **Organization provides API keys** and store a key per provider. Optionally set the **scope** to a group.',
        '**Who pays**: the **Billing** card on every project page tells you. *Organization covers the costs* when the organization provides keys; otherwise *runs on your own API key*.',
        'On group projects the group key is used first, then the organization key. Never another group’s key.',
      ],
    },
    tips: {
      de: [
        'Sie sehen nur Modelle von Anbietern, für die ein Schlüssel vorhanden ist. Fehlt ein Anbieter im Modell-Picker, fehlt der Schlüssel.',
        'Stellt die Organisation Schlüssel bereit, ist das Formular für eigene Schlüssel im Profil abgeschaltet. Das ist beabsichtigt.',
        'Für Klausuren, die Studierende in Vertretbar lösen, wird die KI-Korrektur nicht über deren Schlüssel abgerechnet. Zahlt Ihre Organisation, läuft sie über die Organisation, sonst über das Studierenden-Konto.',
      ],
      en: [
        'You only see models of providers for which a key exists. If a provider is missing in the model picker, the key is missing.',
        'If the organization provides keys, the personal key form in the profile is disabled. That is intended.',
        'For exams students solve in Vertretbar, AI grading is not billed to their keys. If your organization pays, it runs on the organization, otherwise on the student account.',
      ],
    },
    pitfalls: {
      de: [
        '**Stellt die Organisation Schlüssel bereit, hat aber keinen für den gewählten Anbieter, gibt es keinen Rückfall auf Ihren eigenen Schlüssel.** Der Anbieter ist dann schlicht nicht verfügbar.',
        'Wer nicht aktives Mitglied der Organisation ist, kann deren Schlüssel nicht nutzen. Dann wird still der eigene Schlüssel belastet.',
        '„Ihr API-Schlüssel ist gültig, hat aber seine Nutzungs- oder Ratenlimits erreicht“ heißt: kein Guthaben oder Rate-Limit beim Anbieter, nicht ein Fehler in BenGER.',
        'Der Schlüssel muss zum Anbieter passen: `sk-…` ist OpenAI, `sk-ant-…` Anthropic, `AI…` Google, `xai-…` Grok.',
      ],
      en: [
        '**If the organization provides keys but has none for the chosen provider, there is no fallback to your own key.** The provider is simply unavailable.',
        'Anyone who is not an active member of the organization cannot use its keys. Their own key is charged silently instead.',
        '“Your API key is valid but has reached its usage or rate limits” means: no credit or a rate limit at the provider, not an error in BenGER.',
        'The key must match the provider: `sk-…` is OpenAI, `sk-ant-…` Anthropic, `AI…` Google, `xai-…` Grok.',
      ],
    },
    links: [
      { label: { de: 'Profil', en: 'Profile' }, href: '/profile' },
      { label: { de: 'Eigene Modelle registrieren', en: 'Registering custom models' }, href: '/how-to#custom-models' },
    ],
    keywords: { de: ['API-Schlüssel', 'API Key', 'Schlüssel', 'OpenAI', 'Anthropic', 'Google', 'Mistral', 'Guthaben', 'Abrechnung', 'wer zahlt', 'Organisation stellt'], en: ['api key', 'key', 'openai', 'anthropic', 'credits', 'billing', 'who pays', 'organization provides'] },
  },
  {
    id: 'custom-models',
    category: 'generation',
    title: { de: 'Wie binde ich ein eigenes Modell an (BYOM, OpenAI-kompatibler Endpunkt)?', en: 'How do I connect my own model (BYOM, OpenAI-compatible endpoint)?' },
    summary: {
      de: 'Unter [Modelle](/models) → **Eigenes Modell registrieren**. Sie geben Basis-URL und Modellnamen eines OpenAI-kompatiblen Chat-Completions-Endpunkts an und hinterlegen Ihren Schlüssel dafür. Das Modell steht dann für Generierung und als LLM-Judge zur Verfügung.',
      en: 'Under [Models](/models) → **Register custom model**. Enter base URL and model name of an OpenAI-compatible chat-completions endpoint and store your key for it. The model is then available for generation and as an LLM judge.',
    },
    steps: {
      de: [
        '[Modelle](/models) → Abschnitt *Meine Modelle* → **Eigenes Modell registrieren**.',
        '**Anzeigename**, **Basis-URL** (z.B. `https://api.example.com/v1`), **Modellname am Endpunkt** (der Wert im Feld `model`).',
        '**API-Schlüssel erforderlich** ausschalten, wenn der Endpunkt ohne Authentifizierung erreichbar ist (z.B. ein lokaler Server). Sonst **Dein API-Schlüssel** eintragen.',
        'Optional Reasoning-Parameter und Kosten pro Million Tokens (für Kostenberichte). **Testen**, dann speichern.',
        'Teilen: In der Modellliste die Sichtbarkeit auf Organisation oder öffentlich setzen. Geteilt wird nur die Endpunkt-Definition. Jede Person hinterlegt ihren eigenen Schlüssel.',
      ],
      en: [
        '[Models](/models) → section *My models* → **Register custom model**.',
        '**Display name**, **base URL** (e.g. `https://api.example.com/v1`), **model name at the endpoint** (the value of the `model` field).',
        'Switch off **API key required** if the endpoint is reachable without authentication (e.g. a local server). Otherwise enter **Your API key**.',
        'Optionally reasoning parameters and cost per million tokens (for cost reports). **Test**, then save.',
        'Sharing: in the model list set the visibility to organization or public. Only the endpoint definition is shared. Everyone stores their own key.',
      ],
    },
    pitfalls: {
      de: [
        'Adressen im internen Netz (localhost, private IP-Bereiche) sind aus Sicherheitsgründen gesperrt. Der Endpunkt muss öffentlich erreichbar sein.',
        'Über `http://` statt `https://` wird der Schlüssel bei jeder Anfrage im Klartext übertragen.',
        'Eigene Modelle sind konservativ eingestellt: keine garantierte strukturierte Ausgabe, kein Seed. Für Klausur-Bewertungen (Judges) sind Katalogmodelle zuverlässiger.',
        'Löschen deaktiviert das Modell nur, wenn es bereits in Ergebnissen referenziert wird. Es bleibt in alten Läufen sichtbar.',
      ],
      en: [
        'Addresses on internal networks (localhost, private IP ranges) are blocked for security reasons. The endpoint must be publicly reachable.',
        'Over `http://` instead of `https://` the key travels in clear text with every request.',
        'Custom models are configured conservatively: no guaranteed structured output, no seed. For exam grading (judges) catalog models are more reliable.',
        'Deleting only deactivates the model if results already reference it. It stays visible in old runs.',
      ],
    },
    keywords: { de: ['eigenes Modell', 'BYOM', 'Endpunkt', 'Ollama', 'vLLM', 'Basis-URL', 'Community-Modelle'], en: ['custom model', 'BYOM', 'endpoint', 'ollama', 'vllm', 'base url', 'community models'] },
  },
]
