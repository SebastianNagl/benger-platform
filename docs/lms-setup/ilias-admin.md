# ILIAS-Administration: BenGER als LTI-Tool einbinden

Für: die ILIAS-Administration der Hochschule. Getestet mit ILIAS 10.9.
Bezeichnungen in der deutschen Oberfläche, die englische steht in Klammern.
Die drei URLs schickt Ihnen der Organisations-Admin; hier steht dafür
`<tool>`.

## Variante A: globaler Provider (empfohlen)

### 1. Lernfortschritt einschalten (einmalig)

1. **Administration** → **Lernerfolge** → **Zugriffsstatistiken und
   Lernfortschritt** → **Einstellungen**.
2. Bei **Tracking aktivieren** **Lernfortschritt** anhaken → Speichern.

### 2. Provider anlegen

1. **Administration** → **ILIAS erweitern** (*Extending ILIAS*) → **LTI**.
2. Reiter **ILIAS als LTI-Konsument** (*ILIAS as LTI Consumer*).
3. **Globalen Provider für alle Benutzer hinzufügen** (*Add Global Provider
   for all Users*).
4. Felder setzen. Zwei Voreinstellungen sind falsch, sie sind mit ⚠
   markiert.

| Feld | Wert |
|---|---|
| Titel (*Title*) | z. B. `BenGER` |
| ⚠ Verfügbarkeit (*Availability*) | **in neuen und bestehenden Objekten** (*For Creating Objects*) |
| ⚠ LTI Version | **Version 1.3** |
| Login URL | `<tool>/api/lti/launch` |
| Initiate Login URL | `<tool>/api/lti/login` |
| Redirection URI | `<tool>/api/lti/launch` |
| Typ des öffentlichen Schlüssels (*Public Key Type*) | **URL (Json Web Token)**, im Feld URL `<tool>/api/lti/jwks`. Keinen RSA-Schlüssel. |
| Unterstützung für Deep Linking (*Support for Deep Linking*) | **aus** |
| Erweiterte Benotungsdienste (*Advanced Grading Services*) | **an** |
| Identifikation der Person (*User identification*) | **ID des ILIAS-Kontos kombiniert mit einer eindeutigen ILIAS-Plattform-ID …** (die erste Option). Nie **E-Mail-Adresse**. |
| Anmeldename (*User name*) | **Vollständiger Name** (*Entire name*) |
| Provider unterstützt Outcome Service (*Provider supports Outcome Service*) | **an** |
| Voreinstellung Mastery Score (*Default Mastery Score*) | **22** |

5. **Speichern**. ILIAS zeigt wieder die Provider-Liste.

### 3. Werte melden

1. Den Provider in der Liste über seinen Titel öffnen.
2. Unter **Erweiterte Benotungsdienste** steht das Feld **Hinweise**
   (*Hints*) mit **Client ID** und **Deployment ID**.
3. Beide Werte und die Adresse Ihres ILIAS (z. B. `https://ilias.uni-x.de`)
   an den Organisations-Admin schicken.

**Fertig, wenn** der Organisations-Admin „ILIAS ist verbunden.“ meldet.

### 4. Im Kurs (Lehrende oder Administration)

1. Kurs öffnen → **Neues Objekt hinzufügen** (*Add New Object*) →
   **LTI-Konsument** (*LTI Consumer*).
2. Den BenGER-Provider anklicken.
3. **Online** anhaken. **Optionen für den Start** (*Options for Launch*):
   **Neues Fenster** (*New Window*). **Mastery Score**: **22**. Speichern.

Weiter mit der [Anleitung für Lehrende](teacher.md).

## Variante B: nur ein Kurs

Für einen Test ohne globalen Provider. Der Organisations-Admin schickt Ihnen
einen Einladungslink.

1. Kurs öffnen → **Neues Objekt hinzufügen** → **LTI-Konsument**.
2. **Eigene Tool-Einstellungen mit dynamischer Registrierung anlegen (LTI
   1.3)** (*Create Own Settings for Tool with Dynamic Registration*) öffnen.
3. Link bei **Registrierungs-URL des Tools** einfügen → **Anlegen** (*Add*). Der
   Rahmen bleibt kurz leer. Danach nicht mehr abbrechen, der Link ist
   verbraucht.
4. Im vorausgefüllten Formular vor dem Speichern setzen: **Erweiterte
   Benotungsdienste an**, **Identifikation** und **Anmeldename** wie in der
   Tabelle oben, **Outcome Service an**, **Mastery Score 22**.
5. **Speichern** → im Objekt **Online** anhaken, **Neues Fenster** →
   Speichern.

## Wenn etwas nicht klappt

| Was Sie sehen | Ursache | Lösung |
|---|---|---|
| Der Provider fehlt beim Anlegen des Objekts | Verfügbarkeit „nicht verfügbar“ | Verfügbarkeit auf „in neuen und bestehenden Objekten“ |
| Keine Note in ILIAS | Erweiterte Benotungsdienste aus | Im Provider einschalten |
| Noten scheitern mit „User not available“ | Identifikation per E-Mail-Adresse | Auf „ID des ILIAS-Kontos …“ stellen, vor dem ersten Start |
| Lernfortschritt fehlt | Tracking aus oder Outcome Service aus | Schritt 1 und Outcome Service prüfen |
| „ERROR_OPEN_SSL_CONF“ | Irgendein Fehler beim Token-Abruf | JWKS-URL als URL eintragen, nicht als RSA-Schlüssel; `<tool>` von ILIAS aus erreichbar (Port 443) |
