# Groundlift Event Redirect (Odoo 19)

Dieses Modul leitet die Odoo-Eventübersicht

`https://groundlift.odoo.com/event`

per HTTP **301 (permanent)** auf

`https://groundlift.de/public-events.php`

weiter.

## Nicht betroffen

- Event-Detailseiten wie `/event/<event-slug>`
- Registrierungs- und Ticketseiten
- Event-Paginierung und Tag-Filter
- Der Alias `/events`

## Installation auf Odoo.sh

1. Den Ordner `groundlift_event_redirect` in das GitHub-Repository unter den eigenen Addons ablegen.
2. Committen und auf den gewünschten Odoo.sh-Branch pushen.
3. In Odoo den Entwicklermodus aktivieren.
4. Unter **Apps** die App-Liste aktualisieren.
5. Nach **Groundlift Event Redirect** suchen und das Modul installieren.
6. `/event` in einem privaten Browserfenster testen.

## Technische Hinweise

Das Modul hängt von `website_event` ab und erweitert dessen Controller. Nur der
exakte Pfad `/event` beziehungsweise `/event/` wird umgeleitet. Die Zieladresse
kann in `controllers/main.py` über die Konstante `REDIRECT_URL` geändert werden.
