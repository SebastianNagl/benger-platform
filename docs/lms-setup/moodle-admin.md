# Moodle-Administration: BenGER als LTI-Tool einbinden

Für: die Moodle-Administration der Hochschule. Getestet mit Moodle 4.5.
Bezeichnungen in der deutschen Oberfläche, die englische steht in Klammern.
Der Organisations-Admin schickt Ihnen einen Einladungslink. Er funktioniert
einmal und gilt 14 Tage.

## 1. Tool registrieren

1. **Website-Administration** → **Plugins** → **Aktivitäten** → **Externes
   Tool** → **Tools verwalten** (*Site administration → Plugins → Activity
   modules → External tool → Manage tools*).
2. Link bei **LTI Advantage hinzufügen** (*Add LTI Advantage*) einfügen →
   **Hinzufügen**.
3. Fragt Moodle nach einem vorhandenen Tool: **Als neues externes Tool
   registrieren** (*Register as a new external tool*).
4. Das Tool erscheint als **Wartend** (*Pending*) → **Aktivieren**
   (*Activate*).

## 2. Drei Einstellungen ändern

Auf der Tool-Karte das Symbol **Bearbeiten** klicken. Moodle setzt diese
Werte bei jeder Registrierung per Link falsch.

| Einstellung | Wert |
|---|---|
| Verwendung der Toolkonfiguration (*Tool configuration usage*) | **In Aktivitätsauswahl und als vorkonfiguriertes Tool anzeigen** (*Show in activity chooser and as a preconfigured tool*) |
| Standard-Startcontainer (*Default launch container*) | **Neues Fenster** (*New window*) |
| Bewertungen aus dem Tool akzeptieren (*Accept grades from the tool*) | **Immer** (*Always*) |

Prüfen, sonst nichts ändern:

| Einstellung | Wert |
|---|---|
| Datenschutz: Name und E-Mail-Adresse an das Tool (*Share launcher's name with tool*, *Share launcher's email with tool*) | **Immer** (*Always*) |
| IMS LTI Aufgaben und Bewertung (*IMS LTI Assignment and Grade Services*) | **Service für die Synchronisation von Bewertungen und die Verwaltung der Spalten nutzen** (*Use this service for grade sync and column management*) |

**Speichern**.

Die Spaltenverwaltung braucht BenGER für die Spalte **KI-Bewertung** und
dafür, dass Lehrende eine ganze Klausurensammlung mit einer Aktivität
verknüpfen können. Dann legt BenGER je Aufgabe eine eigene Spalte an, und
die Spalte der Aktivität erhält den Mittelwert. Mit **Service nur für
Bewertungen nutzen** (*Use this service for grade sync only*) erhält Moodle
nur die Endnote, und Lehrende können eine Sammlung nur Aufgabe für Aufgabe
mit je einer Aktivität verknüpfen.

**Fertig, wenn** der Organisations-Admin die Anbindung als **Anbindung
aktiv** sieht. Weiter mit der [Anleitung für Lehrende](teacher.md).

## Wenn etwas nicht klappt

| Was Sie sehen | Ursache | Lösung |
|---|---|---|
| Lehrende finden das Tool nicht | Verwendung der Toolkonfiguration | Auf „In Aktivitätsauswahl …“ stellen |
| Personen landen auf einer Anmeldeseite | Tool startet eingebettet | Standard-Startcontainer „Neues Fenster“ |
| Aktivitäten haben keine Bewertung | Bewertungen werden an Lehrende delegiert | „Bewertungen aus dem Tool akzeptieren“ auf „Immer“ |
| Nur die Endnote, keine Spalte „KI-Bewertung“ | AGS nur für die Synchronisation | „… und die Verwaltung der Spalten nutzen“ |
| Lehrende können die ganze Klausurensammlung nicht wählen (`collection_unsupported`) | AGS nur für die Synchronisation | „… und die Verwaltung der Spalten nutzen“, dann die Aktivität neu öffnen |
| Der Link ist abgelaufen oder verbraucht | Einmal-Link | Neuen Link beim Organisations-Admin anfordern |
