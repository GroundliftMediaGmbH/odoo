# Groundlift Event Redirect – Odoo 19

Dieses Modul leitet die öffentliche Odoo-Eventübersicht

`https://groundlift.odoo.com/event`

auf

`https://groundlift.de/public-events.php`

weiter.

## Version 19.0.1.1.1

Diese Version behebt den Installationsfehler:

`View inheritance may not use attribute 'title' as a selector.`

Die vorherige View suchte die Odoo-Links über die übersetzbaren Attribute
`title="All Events"` und `title="Back to All Events"`. Odoo 19 verbietet
übersetzbare Attribute als XPath-Selektoren.

Die korrigierte Version:

- verwendet stabile strukturelle Selektoren für die mobile und die Desktop-Navigation;
- setzt die beiden Odoo-Links „Alle Veranstaltungen“ auf die externe Groundlift-Seite;
- öffnet externe Links mit `target="_top"` außerhalb des Website-Preview-iFrames;
- führt im authentifizierten Odoo-Website-iFrame keine Cross-Domain-Weiterleitung aus;
- leitet normale öffentliche Aufrufe von `/event` weiterhin per HTTP 302 weiter;
- verändert keine Event-Detail-, Ticket- oder Registrierungsseiten.

## Installation auf Odoo.sh

1. Den vorhandenen Ordner `groundlift_event_redirect` im GitHub-Repository vollständig ersetzen.
2. Committen und auf den gewünschten Odoo.sh-Branch pushen.
3. Den erfolgreichen Build abwarten.
4. In Odoo **Apps** öffnen.
5. Den Filter **Apps** entfernen, falls das Modul nicht angezeigt wird.
6. Nach **Groundlift Event Redirect** suchen.
7. Das Modul installieren beziehungsweise **Upgrade/Aktualisieren** ausführen.
8. Website-Vorschau und Browserseite neu laden.

## Browserhinweis

Eine frühere Modulversion verwendete möglicherweise eine permanente
301-Weiterleitung. Browser können diese lokal zwischenspeichern. Bei abweichendem
Testverhalten bitte ein privates Browserfenster verwenden oder den Cache für die
Odoo-Staging-Domain löschen.
