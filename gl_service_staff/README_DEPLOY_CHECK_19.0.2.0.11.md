# Groundlift Servicepersonal – Deploymentprüfung 19.0.2.0.11

Dieses Release enthält **die gleichen Layout-Funktionen wie 19.0.2.0.10**. 
Zusätzlich wird die Vorlage im HTML der Mitarbeiterseite mit `data-gl-service-layout="19.0.2.0.11"` gekennzeichnet. Damit lässt sich unterscheiden, ob Odoo die tatsächliche Website-Vorlage aktualisiert hat (und nicht nur die Modulversionsnummer).

## Installation auf Odoo.sh

1. Im tatsächlich an Odoo.sh angebundenen Git-Branch den Modulordner `gl_service_staff` vollständig ersetzen. **Nicht** nur das ZIP als Datei ins Git-Repository kopieren.
2. Sicherstellen, dass neben `__manifest__.py` auch `views/portal_templates.xml` und `controllers/portal.py` im Commit enthalten sind.
3. Änderungen **committen und pushen** (oder auf GitHub mit Commit speichern). Ohne neuen Commit am angebundenen Branch wird kein neuer Odoo.sh-Build gestartet.
4. In Odoo.sh im Staging-Zweig die erzeugte Build-Revision überprüfen. Mit `Rebuild` kann derselbe Git-Stand erneut gebaut werden; das ersetzt keinen fehlenden Git-Commit.
5. Nach erfolgreichem Build/Modulupdate Seite `/servicepersonal` neu laden, ggf. in Inkognito. HTML-Quelltext/Elemente auf `data-gl-service-layout="19.0.2.0.11"` prüfen.
6. Fehlt der Marker, das zugehörige XML in der Datenbank prüfen: externes ID `gl_service_staff.portal_service_staff_home` (`ir.ui.view`). Die Diagnosehilfe `odoo_serviceportal_diagnose.py` ist separat verfügbar und nur lesend.

## Layoutänderungen

- Kalenderabonnement in einem zugeklappten Abschnitt **nach allen** Terminkarten.
- Jede Veranstaltung und jedes Projekt als abgesetzte, orange akzentuierte Karte.
- Kollegenliste **unter** den Rückmeldungen am Ende jeder Karte.
- Kollegen nur mit Name und lokaler Berliner Uhrzeit, ohne Datum.
- Chronologische gemischte Event-/Projekt-Reihenfolge bleibt erhalten.

## Wichtige Diagnosehinweise

Die installierte Modulversion ist **kein Beweis**, dass die QWeb-Vorlage in der Datenbank aktualisiert wurde.
Das Website-Template liegt in `ir.ui.view`; Änderungen an `views/portal_templates.xml` erfordern ein Modulupgrade.
Ein neuer Git-Commit löst einen Odoo.sh-Build aus. Ein reiner Datei-Upload in den laufenden Container bzw. ein nicht committeter Editorwechsel hingegen nicht.
Eine manuelle, geerbte oder website-spezifische View kann die Hauptvorlage überlagern; Diagnosehilfe prüft geerbte aktive Views.

Keine Geschäftslogik geändert und keine Datenmigration durch dieses Release.
