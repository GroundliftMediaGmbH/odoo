# Groundlift Servicepersonal – Hotfix 19.0.2.0.9

Ausgangsbasis: vollständige Version 19.0.2.0.8. Alle dortigen Funktionen bleiben enthalten.

## Behobener Fehler

Die Mitarbeiteransicht `/servicepersonal` zeigte ein Projekt vom November 2026
hinter einer Veranstaltung vom November 2027. Der Sortierschlüssel verwendete
bei Personalzeilen **ohne** `planned_start_datetime` das technische Feld
`shift.start_datetime`, während der sichtbare Projekt-Karteninhalt das Feld
`shift.shift_date` verwendete. Sind diese beiden Felder nicht synchron, ist
der Sortierschlüssel nicht identisch mit dem sichtbaren Termin.

**Neues Verhalten:** `planned_start_datetime` (falls vorhanden; lokalisiert
nach `Europe/Berlin`), sonst `shift_date` bei nur datierten Einträgen.
Projekte, Veranstaltungen und manuelle Schichten werden aus einer gemeinsamen
Liste sortiert. Datensätze mit nur einem Datum stehen zu Beginn des entsprechenden
Tages. Gleichstände sind nach Schicht-ID und Zeilen-ID stabil sortiert.

Es werden **keine** Datenbank-Termine geändert und **keine** E-Mails gesendet.
Die Änderung betrifft nur die Reihenfolge der Karten in der Mitarbeiteransicht.

## Installation

Kompletten Modulordner `gl_service_staff` aus dem ZIP im Odoo.sh-Repository
ersetzen, vorzugsweise zuerst auf Staging. Die App aktualisieren. Danach die
Mitarbeiterseite `/servicepersonal` neu laden (ggf. Strg+F5).

## Abnahme

- Projekt am 20.11.2026 (nur Datum) muss vor der Veranstaltung 11.11.2027 stehen.
- Projekt 20.11.2026 muss unter anderen Einsätzen im November 2026 einsortiert sein.
- Bei mehreren Einsätzen am selben Tag wird nach der angezeigten Anfangsuhrzeit sortiert,
  sofern eine solche vorhanden ist; Einträge ohne Uhrzeit stehen zuerst.
- Anmeldung, Antworten, Kollegen, Kalenderabonnement, Erinnerungen und E-Mail-Freigaben
  bleiben unberührt.

Offline getestet: Sortierung mit gemischten Projekt-/Veranstaltungsfällen,
Sommer-/Winterzeit; Python und XML. Vollständiger Odoo.sh-Integrationstest ist
auf Staging durchzuführen.
