# OpenOlat-Administration: BenGER als LTI-Tool einbinden

Für: die OpenOlat-Administration der Hochschule. Getestet mit OpenOlat 21.1.2.
Bezeichnungen in der deutschen Oberfläche, die englische steht in Klammern.
Die drei URLs schickt Ihnen der Organisations-Admin; hier steht dafür
`<tool>`. OpenOlat kennt keine Registrierung per Link, das Tool wird einmal
von Hand angelegt und gilt dann für alle Kurse.

## 1. LTI 1.3 einschalten (einmalig)

1. *Administration* → *Externe Werkzeuge* (*External tools*) → *LTI*.
2. Reiter *Konfiguration*: *Modul „LTI 1.3"* einschalten → Speichern.

## 2. Tool anlegen

1. Reiter *Externe Tools* (*External tools*) → *Neues Tool hinzufügen*
   (*Create a new tool*).
2. Felder setzen. Zwei Einstellungen lassen sich später nicht mehr ändern
   oder sind voreingestellt falsch, sie sind mit ⚠ markiert.

| Feld | Wert |
|---|---|
| Name des Tools (*Tool Name*) | z. B. `BenGER` |
| Tool URL | `<tool>/api/lti/launch` |
| ⚠ Mit Shared Deployment (*With shared deployment*) | an. Lässt sich nach dem Speichern nicht mehr ändern. Ohne Shared Deployment bekommt jede LTI-Seite eine eigene Client-ID und Deployment ID. |
| ⚠ Öffentlicher Schlüsseltyp (*Public Key Type*) | *Schlüsselsatz-URL* (*URL*), im Feld darunter `<tool>/api/lti/jwks`. Keinen RSA-Schlüssel. |
| URL der Authentifizierungsanforderung (*Initiate login URL*) | `<tool>/api/lti/login` |
| Umleitungs-URI(s) (*Redirection URI(s)*) | `<tool>/api/lti/launch` |
| Deep-Linking aktivieren (*Activate Deep-Linking*) | an |

3. Speichern.

## 3. Werte melden

Die Liste der externen Tools zeigt nach dem Speichern über *Bearbeiten*
(*Edit*) diese Werte. Schicken Sie sie an den Organisations-Admin:

| Wert in OpenOlat | Wofür |
|---|---|
| Client-ID (*Client ID*) | Client ID der Anbindung |
| Deployment ID | Deployment ID der Anbindung |
| Plattform-ID (*Platform ISS*) | Adresse (Issuer) der Anbindung, z. B. `https://olat.uni-x.de` |

Die Endpunkte (`/lti/auth`, `/lti/token`, `/lti/keys`) setzt BenGER aus der
Plattform-ID selbst zusammen. Der Organisations-Admin trägt die drei Werte im
Panel *Lernplattform verbinden* → *OpenOlat* ein; die Anbindung ist danach
sofort aktiv.

## 4. Was Lehrende im Kurs einstellen

Steht ausführlich in der [Anleitung für Lehrende](teacher.md). Kurz:

- Kursbaustein *LTI-Seite* einfügen, im Reiter *Seiteninhalt* bei *LTI
  Version* das Tool `BenGER` wählen und einmal speichern.
- *Inhalt auswählen* öffnet die Klausurauswahl von BenGER direkt in OpenOlat.
- *Vorname/Name übertragen* und *E-Mail-Adresse übertragen* einschalten.
- *Anzeige*: *Neues Fenster öffnen*. Eingebettet zeigt BenGER erst eine Seite
  mit einem Knopf für das neue Fenster.
- *Konfiguration Bewertung*: *Punkte übertragen* an, *Skalierungsfaktor* 1,
  *Notwendige Punktzahl für „bestanden"* 4 (Notenpunkte) oder 10
  (französische Note auf 20).

## Grenzen von OpenOlat 21

- Das Tool bekommt je LTI-Seite eine Notenspalte. Weitere Spalten (die
  KI-Bewertung, eine Spalte je Aufgabe einer Klausurensammlung) lehnt
  OpenOlat ab; eine Sammlung wird deshalb Aufgabe für Aufgabe mit je einer
  LTI-Seite verknüpft.
- OpenOlat übernimmt die Punkte unverändert und zeigt den Kommentar zur Note
  nicht an. Das Feedback steht in BenGER.
- Ohne *Vorname/Name übertragen* und *E-Mail-Adresse übertragen* starten
  Teilnehmende anonym. BenGER fragt dann einmal nach einer E-Mail-Adresse.
