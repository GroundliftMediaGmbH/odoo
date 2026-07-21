# Validierung

Vor der Auslieferung wurden folgende statische Prüfungen ausgeführt:

- Python-Kompilierung aller Moduldateien (`compileall`)
- Python-AST-Prüfung aller `.py`-Dateien
- XML-Parsing aller Sicherheits-, Daten-, Backend- und QWeb-Dateien mit `lxml`
- Prüfung der dynamischen QWeb-Ausdrücke und Formularrouten
- Prüfung der ZIP-Struktur und des Modul-Manifests
- Prüfung, dass Felder aus Such-Domains gespeichert oder über eine Suchmethode durchsuchbar sind
- Prüfung der Odoo-19-Anwesenheitsfelder und des direkten, versionsbezogenen `structure_type_id`-Filters
- Prüfung der responsiven Portalstruktur für Login, Monatsübersicht, Mitarbeiterdetails und Tagesprüfung

Eine echte Installation gegen eine laufende Odoo-19-Instanz war in der Erstellungsumgebung nicht verfügbar. Das Upgrade sollte deshalb zunächst auf einem Odoo.sh-Staging-Branch erfolgen.

## Version 19.0.1.0.6

- Python-Syntax aller Moduldateien geprüft
- Sämtliche XML-Dateien auf Wohlgeformtheit geprüft
- Manifest und ZIP-Struktur geprüft
- Vollständig gekapselte Portal-CSS-Regeln ergänzt
- Inline-Einbindung der Portal-Styles geprüft
- Website-Header-/Footer-Ausblendung auf den Prüfseiten geprüft
- Theme-unabhängige `<details>`-Mitarbeiteransicht geprüft
- Mobile Breakpoints und horizontal scrollbar ausgeführte Tagesübersicht geprüft

## Version 19.0.1.0.7

- QWeb-Statuspriorität `paid` vor `approval_state` geprüft
- Status **Überwiesen** in der zusammengeklappten Mitarbeiterkarte geprüft
- Inline- und Asset-CSS für den neuen Zahlungsstatus synchronisiert
- Python-Syntax, XML-Wohlgeformtheit, Manifest und ZIP-Struktur geprüft
