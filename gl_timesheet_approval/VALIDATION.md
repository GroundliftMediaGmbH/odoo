# Validierung

Vor der Auslieferung wurden folgende statische Prüfungen ausgeführt:

- Python-Kompilierung aller Moduldateien (`compileall`)
- Python-AST-Prüfung aller `.py`-Dateien
- XML-Parsing aller Sicherheits-, Daten-, Backend- und QWeb-Dateien mit `lxml`
- Syntaxprüfung der dynamischen QWeb-Ausdrücke
- Prüfung der ZIP-Struktur und des Modul-Manifests

Eine echte Installation gegen eine laufende Odoo-19-Instanz war in der Erstellungsumgebung nicht verfügbar. Die erste Installation sollte deshalb – wie bei Custom-Modulen üblich – zunächst auf einem Odoo.sh-Staging-Branch erfolgen.
