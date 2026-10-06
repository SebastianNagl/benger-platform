# Lehrende: Aktivität anlegen und Klausur verknüpfen

Für: Lehrende eines Kurses in Moodle oder ILIAS. Die Anbindung hat die
Administration schon eingerichtet.

## 1. Aktivität anlegen

- **Moodle**: **Aktivität anlegen** → BenGER in der Aktivitätsauswahl →
  Bewertung eingeschaltet lassen (Maximum 100 ist in Ordnung) → Speichern.
- **ILIAS**: **Neues Objekt hinzufügen** → **LTI-Konsument** → den
  BenGER-Provider wählen → **Online** anhaken, **Optionen für den Start**:
  **Neues Fenster**, **Mastery Score** 22 → Speichern.

## 2. Klausur verknüpfen (einmal)

1. Die Aktivität öffnen (ILIAS: **Inhalt anzeigen**). BenGER öffnet sich in
   einem neuen Fenster.
2. Beide Zustimmungen anhaken → **Weiter**.
3. Nur ILIAS: E-Mail-Adresse eintragen oder **Überspringen**.
4. Eine Klausur wählen, oder **Oder neue Klausur anlegen**: Titel, Angabe
   (Sachverhalt) und Musterlösung eintragen → **Klausur erstellen**.
   Hat die Klausur eine Aufgabe, ist die Aktivität automatisch mit dieser
   Aufgabe verknüpft. Für eine Klausurensammlung siehe Abschnitt 3.
5. **Verknüpfen**.

**Fertig, wenn** die Seite der Klausur erscheint, mit der Karte
**Lernplattform-Aktivitäten**.

## 3. Klausurensammlung verknüpfen

Eine Klausurensammlung ist eine Klausur mit mehreren Aufgaben. Es gibt zwei
Wege.

**Weg A: eine Aktivität je Aufgabe (Moodle und ILIAS)**

1. Für jede Aufgabe eine eigene Aktivität anlegen (Abschnitt 1). Ein
   sprechender Titel hilft, z. B. „Klausur Strafrecht, Aufgabe 2“.
2. Die Aktivität öffnen → die Sammlung in der Auswahl aufklappen → die
   Aufgabe wählen → **Verknüpfen**.
3. Für die nächste Aufgabe mit der nächsten Aktivität wiederholen.

Jede Aktivität erhält nur die Note ihrer Aufgabe. Die Studierenden
erreichen trotzdem alle Aufgaben der Sammlung.

**Weg B: die ganze Sammlung in einer Aktivität (nur Moodle)**

1. Eine Aktivität anlegen (Abschnitt 1).
2. Die Aktivität öffnen → in der Auswahl statt einer Aufgabe die ganze
   Sammlung wählen → **Verknüpfen**.
3. BenGER legt im Moodle-Notenbuch je Aufgabe eine Spalte an, „Aufgabe N:
   Titel der Aktivität“, und, solange KI-Noten übertragen werden, je
   Aufgabe eine Spalte „KI-Bewertung: Aufgabe N“. Die Spalten erscheinen mit
   der ersten Note der Aufgabe.
4. Die Spalte der Aktivität erhält den Mittelwert der Endnoten aller
   Aufgaben. Er wird erst gesendet, wenn jede Aufgabe eine Endnote hat.
   Vorher bleibt die Spalte leer.
5. Kursgesamtbewertung prüfen: Moodle zählt jede Spalte mit. Soll nur der
   Mittelwert zählen, setzen Sie bei jeder Spalte „Aufgabe N“ und
   „KI-Bewertung“ die Gewichtung auf 0 (wie in Abschnitt 4).

Weg B gibt es nur, wenn die Moodle-Administration beim Tool **Service für
die Synchronisation von Bewertungen und die Verwaltung der Spalten nutzen**
eingestellt hat. In ILIAS gibt es Weg B nicht, dort gilt Weg A.

**Gut zu wissen**

- Eine neue Aufgabe in der Sammlung erhält bei Weg B ihre Spalten mit der
  nächsten Übertragung. Bis sie bewertet ist, wartet der Mittelwert.
- Importe in die Klausur sind möglich, solange keine Aktivität mehr die
  ganze Klausur als eine Note erhält (ältere Verknüpfungen vor Weg A und B).
  Eine solche ältere Verknüpfung lässt sich jederzeit mit der einzigen
  Aufgabe der Klausur verknüpfen.
- Die Verknüpfung (andere Klausur, andere Aufgabe, Wechsel zwischen Weg A
  und B) lässt sich ändern, bis die erste Note in der Lernplattform
  angekommen ist. Danach legen Sie eine neue Aktivität an.

## 4. Später

- Die Aktivität öffnen führt immer auf die Seite der Klausur.
- **Lernplattform-Aktivitäten** → **Übersicht öffnen**: alle Abgaben,
  KI-Note, Korrektur und was die Lernplattform erhalten hat.
- **Korrektur öffnen**: Bewertungsbogen ausfüllen → **Bewertung speichern**.
  Ihre Note ersetzt die KI-Note in der Lernplattform.
- Moodle: die Spalte **KI-Bewertung** aus der Kursgesamtbewertung nehmen:
  **Bewertungen** → **Setup für Bewertungen** → in der Zeile KI-Bewertung
  bei **Gewichtungen** anhaken, 0 eintragen → **Änderungen speichern**.

## Wenn etwas nicht klappt

| Was Sie sehen | Ursache | Lösung |
|---|---|---|
| Klausur ist in der Auswahl ausgegraut | Keine Aufgabe, keine Notenpunkte oder kein aktiver Bewertungsbogen | Grund steht daneben |
| Die Auswahl verlangt eine Aufgabe (`task_required`) | Die Klausur ist eine Klausurensammlung | Aufgabe wählen (Weg A) oder in Moodle die ganze Sammlung (Weg B) |
| Die ganze Sammlung lässt sich nicht wählen (`collection_unsupported`) | ILIAS, oder Moodle darf keine Spalten anlegen | Weg A nutzen, oder die Moodle-Administration stellt die Spaltenverwaltung ein |
| Spalte der Aktivität bleibt leer (Weg B) | Noch nicht jede Aufgabe hat eine Endnote | Fehlende Aufgaben bewerten; der Mittelwert folgt dann |
| Studierende sehen „noch nicht verknüpft“ | Noch keine Klausur verknüpft | Schritt 2 |
| Keine Note in der Lernplattform | Aktivität ohne Bewertung | Moodle: Bewertung einschalten; ILIAS: Administration fragen |
| Verknüpfung lässt sich nicht ändern | Es wurden schon Noten übertragen | Neue Aktivität anlegen |
