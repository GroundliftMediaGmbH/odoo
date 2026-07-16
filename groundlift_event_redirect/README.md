# Groundlift Event Redirect – Odoo 19

Dieses Modul leitet die öffentliche Odoo-Eventübersicht

`https://groundlift.odoo.com/event`

auf

`https://groundlift.de/public-events.php`

weiter.

## Version 19.0.1.1.0

Diese Version behebt den Fehler des Odoo-Website-Builders:

`Cannot read properties of null (reading 'body')`

Der Fehler entstand, weil Odoo seine Website im Backend in einem iframe anzeigt
und die frühere Weiterleitung dieses iframe auf eine andere Domain geschickt
hat. Die neue Version:

- setzt die Odoo-Links „Alle Veranstaltungen“ direkt auf die externe Groundlift-Seite;
- öffnet diese Links im Website-Preview korrekt außerhalb des iframe;
- führt im Odoo-Website-iframe keine Cross-Domain-Weiterleitung mehr aus;
- leitet normale öffentliche Aufrufe von `/event` weiterhin weiter;
- verändert keine Event-Detail-, Ticket- oder Registrierungsseiten.

## Update auf Odoo.sh

1. Den vorhandenen Ordner `groundlift_event_redirect` im GitHub-Repository vollständig durch diesen Ordner ersetzen.
2. Committen und auf den gewünschten Odoo.sh-Branch pushen.
3. Warten, bis der Odoo.sh-Build erfolgreich abgeschlossen ist.
4. In Odoo **Apps** öffnen.
5. Den Filter **Apps** entfernen, falls das Modul nicht angezeigt wird.
6. Nach **Groundlift Event Redirect** suchen und **Upgrade/Aktualisieren** ausführen.
7. Die Website-Vorschau neu laden.

## Browserhinweis

Die frühere Modulversion verwendete eine permanente 301-Weiterleitung. Chrome
kann diese lokal zwischenspeichern. Falls ein alter Test weiterhin auftritt,
die Seite in einem privaten Fenster testen oder den Browser-Cache für die
Odoo-Staging-Domain leeren.
