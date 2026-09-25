# Organisations-Admin: Lernplattform verbinden

Für: Admins der Organisation in BenGER (Gruppen-Admins für ihre Gruppen).
Vorher: ein Vertrag mit uns. Eine Anbindung ist sofort aktiv.

## 1. KI-Bewertung vorbereiten

1. **Benutzer & Organisationen** → Reiter **Organisationen** → Ihre
   Organisation wählen.
2. **API-Schlüssel** → **Organisation stellt API-Schlüssel bereit**
   einschalten → einen OpenAI-Schlüssel hinterlegen.
3. **Mehr** → **Lernplattform (LTI)**.
4. Oben steht **KI-Bewertung eingerichtet**. Steht dort ein gelber Hinweis,
   fehlt noch ein Schlüssel.

## 2. Anbindung starten

1. Im Panel **Lernplattform verbinden** klicken.
2. Die Lernplattform wählen und weiter bei 3a (Moodle) oder 3b (ILIAS).
   Für andere Systeme: **Andere** öffnet das vollständige Formular.

## 3a. Moodle

1. **Adresse für die Lernplattform** wählen:
   - **BenGER-Adresse**: Lehrende arbeiten in der Expertenoberfläche.
   - **Studierenden-Adresse**: alle arbeiten in der Studierendenoberfläche.
2. Optional eine **Gruppe** wählen.
3. **Einladungslink erstellen** → Link kopieren. Er wird nur einmal
   angezeigt und gilt 14 Tage.
4. Link an die Moodle-Administration schicken, zusammen mit der
   [Moodle-Anleitung](moodle-admin.md).
5. Bis Moodle den Link einlöst, steht im Panel die Karte **Wartet auf die
   Lernplattform**.

**Fertig, wenn** die Karte verschwunden ist und eine Anbindung mit
**Anbindung aktiv** erscheint.

## 3b. ILIAS

1. **Adresse für die Lernplattform** wählen (siehe 3a) und optional eine
   **Gruppe**.
2. Schritt 1 zeigt drei URLs. Schicken Sie sie an die ILIAS-Administration,
   zusammen mit der [ILIAS-Anleitung](ilias-admin.md).
3. Die ILIAS-Administration meldet **Client ID** und **Deployment ID**.
4. Im Panel wieder **Lernplattform verbinden** → **ILIAS** → **Weiter**.
5. Schritt 2: **ILIAS-Adresse** (z. B. `https://ilias.uni-x.de`), **Client
   ID** und **Deployment ID** eintragen → **Verbinden**.

**Fertig, wenn** Schritt 3 „ILIAS ist verbunden.“ zeigt und die Karte
**Anbindung aktiv** im Panel steht.

Nur einen ILIAS-Kurs testen? In Schritt 1 **Einladungslink erstellen** (siehe
[ILIAS-Anleitung, Variante B](ilias-admin.md#variante-b-nur-ein-kurs)).

## Wenn etwas nicht klappt

| Was Sie sehen | Ursache | Lösung |
|---|---|---|
| Karte **Wartet auf die Lernplattform** bleibt | Die Lernplattform hat den Link nicht eingelöst | Moodle-Administration den Link in „LTI Advantage hinzufügen“ einfügen lassen. Abgelaufen: neuen Link erstellen. |
| Gelber Hinweis zur KI-Bewertung | Kein Schlüssel oder Option aus | Schritt 1 wiederholen |
| **Verbinden** meldet einen Fehler | Adresse, Client ID oder Deployment ID falsch | Werte in ILIAS im Provider unter „Hinweise“ nachsehen |
| Warnung auf der Karte „Notenübertragung nach ILIAS scheitert“ | ILIAS identifiziert per E-Mail-Adresse | ILIAS-Administration: Identifikation auf „ID des ILIAS-Kontos …“ stellen |
