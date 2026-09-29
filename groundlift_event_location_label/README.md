# Groundlift Event Location Label – Odoo 19

Kleines Odoo-19-Modul für die Groundlift Event-Landingpages.

## Funktion

Ersetzt ausschließlich die **sichtbare technische Zeitzonen-Bezeichnung**
`Europe/Berlin` in `website_event.event_description_dates` durch:

**Inning am Ammersee**

Die tatsächliche Zeitzone (`event.date_tz`) wird **nicht verändert**. Damit
bleiben Uhrzeitberechnung, Sommer-/Winterzeit und Kalenderlinks unverändert.

## Version 19.0.1.0.1

Fix für einen Installationsfehler bei mehrtägigen Veranstaltungen. Die beiden
Zeitzonenfelder im Start-/Ende-Block werden nun strukturell eindeutig adressiert,
statt nacheinander per `[1]` und `[2]` ersetzt zu werden.

## Installation / Update

1. Ordner `groundlift_event_location_label` ins Odoo.sh-Repository legen.
2. Commit + Push.
3. In Odoo die App-Liste aktualisieren.
4. Modul installieren bzw. bei bestehender Installation aktualisieren.
