# Groundlift Servicepersonal – Portal-Layout 19.0.2.0.10

Grundlage ist das vollständige Modul 19.0.2.0.9 mit den bisherigen
Funktionen aus 19.0.2.0.7 und 19.0.2.0.8.

## Änderungen auf /servicepersonal

- **Abonnierbarer Kalender-Link ganz unten:** Unterhalb aller Schichtkarten als
  zusammenklappbarer Bereich "Kalender abonnieren (iCal / Google / Outlook)".
  Der bestehende private Kalenderfeed und sein Token bleiben unverändert.
- **Deutliche Veranstaltungskarten:** Projekte und Events bleiben in derselben
  chronologischen Liste. Jede Karte erhält sichtbaren Rahmen, orangefarbene
  linke Markierung, abgerundete Ecken und größeren Abstand zur nächsten Karte.
- **"Wer ist mit mir eingeteilt?" als letzter Kartenabschnitt:** Zuerst werden
  weiterhin Status und ggf. erforderliche Antworten angezeigt. Erst danach
  kommt, durch eine Linie abgetrennt, die bereits bekannte Kollegenliste.
- **Kollegen ohne Datum:** Name sowie `HH:MM–HH:MM Uhr`. Zeiten werden in
  `Europe/Berlin` inklusive Sommer-/Winterzeit ausgegeben. Liegt keine Uhrzeit
  vor, wird nur der Name angezeigt.

## Nicht verändert

- Backend-Modelle, Status, Termin- und Zeitsynchronisierung, Mailversand,
  Kapazität/Absagen, Kalenderfeed, Mitarbeiter-PIN und Tokens.
- Chronologische Sortierung aus 19.0.2.0.9 bleibt erhalten.
- Keine Datenmigration, keine Datensatzänderung oder ausgehende E-Mail durch
  das Modulupdate selbst.

## Einspielen und Abnahme

1. Auf Odoo.sh **Staging** den Modulordner `gl_service_staff` ersetzen.
2. App "Groundlift Servicepersonal" aktualisieren und `/servicepersonal`
   nach Neuladen (ggf. Strg+F5) mit Mitarbeitertestkonto prüfen.
3. Die Kalenderabonnement-Funktion muss unterhalb der letzten Kachel liegen.
4. Jede Schicht hat eine sichtbare eigene Kachel; die Kollegenliste steht ganz unten.
5. Bei Kollegen werden nur Name und **Uhrzeit** angezeigt, auch bei
   24h-übergreifenden Einsätzen. Kalender- und Mailfunktionen bleiben intakt.

Lokale Prüfung: Python-Compile, XML-Parsing, Strukturtests, Zeitzonen-Tests
und ZIP-Prüfung. Odoo.sh-Laufzeittest ist weiterhin auf Staging erforderlich.
