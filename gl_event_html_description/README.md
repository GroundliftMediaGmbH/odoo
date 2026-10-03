# Groundlift Event HTML Description – Odoo 19

Version: **19.0.1.2.0**

## Zweck

Das Modul ergänzt im Veranstaltungs-Backend einen Tab **Website HTML**.

Wichtig: Es wird **kein zweites Beschreibungsfeld** angelegt. Der Tab zeigt direkt Odoos natives Feld
`event.event.description` mit dem Odoo-Code-Editor an.

Damit gilt automatisch:

- Die normale „Event Beschreibung“ und der HTML-Tab sind zwei Ansichten desselben Datenfeldes.
- Bereits vorhandene Veranstaltungsbeschreibungen erscheinen sofort als HTML-Quellcode im neuen Tab.
- Änderungen im HTML-Tab ändern direkt die originale Odoo-Veranstaltungsbeschreibung.
- Die Standard-Eventseite verwendet weiterhin Odoos normalen Rendering-Weg und zeigt genau diesen Inhalt.
- Es gibt keinen QWeb/XPath-Eingriff in die Website-Eventseite.
- Es gibt keine Synchronisationslogik und keine Installations-/Migrationshooks.

## Update von 19.0.1.1.0

Den vorhandenen Modulordner `gl_event_html_description` vollständig durch diese Version ersetzen und die App in Odoo aktualisieren.
Die früheren Python-Dateien sind in dieser ZIP absichtlich als leere Dateien enthalten, damit auch bei einem reinen Überschreiben
keine alte Synchronisationslogik weiter importiert wird.
