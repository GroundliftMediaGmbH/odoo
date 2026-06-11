# Groundlift Servicepersonal Kosten für Odoo 19 SH

Dieses Zusatzmodul erweitert eure bestehende App `gl_service_staff`.

## Funktion

- Es nimmt pro Serviceschicht die Servicekräfte mit `state = accepted` und `role = desired`.
- Pro Person wird gerechnet:

  `Dauer in Stunden = planned_end_datetime - planned_start_datetime`

  `Personalkosten = Dauer × Stündliche Kosten des hr.employee`

- Die Summe aller passenden Serviceschichten wird in das Event-Feld geschrieben:

  `event.event.x_studio_event_kalk_ist_servicepersonal`

## Warum `role = desired`?

Eure Servicepersonal-App fragt bei spontanen Schichten teilweise zusätzliche Reservepersonen an. Diese Reserve-Zusagen werden bewusst nicht mitgerechnet, solange sie nicht wirklich als Wunschpersonal / tatsächlich eingesetztes Servicepersonal hochgezogen wurden.

## Mitarbeiter-Kostenfeld

Primär wird auf `hr.employee.hourly_cost` zugegriffen. Falls das Feld in eurer Datenbank anders heißt, erkennt das Modul zusätzlich mehrere Fallbacks und Studio-Felder mit der Beschriftung „Stündliche Kosten".

## Event-Zuordnung bei Projekt-Schichten

Bei direkten Event-Schichten wird `gl.service.shift.event_id` verwendet.

Bei Projekt-Schichten versucht das Modul, das passende Event über typische Relationen zu finden, z. B.:

- `project.project.event_id`
- `project.project.x_studio_event_id`
- `event.event.project_id`
- `event.event.x_studio_project_id`

Falls keine Relation existiert, wird als sehr konservativer Fallback nur dann nach Name + Datum gematcht, wenn exakt ein Event gefunden wird.

## Installation

1. Ordner `gl_service_staff_event_costs` in euer Custom-Addons-Repository kopieren.
2. Commit + Push auf Odoo.sh.
3. Branch bauen lassen.
4. Apps-Liste aktualisieren.
5. Modul **Groundlift Servicepersonal Kosten** installieren.
6. Optional im Menü **Servicepersonal → Servicekosten neu berechnen** einmal manuell ausführen.

Zusätzlich läuft stündlich ein Cron zur Sicherheitsaktualisierung.
