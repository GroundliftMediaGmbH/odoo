# Groundlift Projekt-Checkliste für Odoo 19 SH

Dieses Modul erweitert `project.project` um Checklisten-Tabs direkt im Projektformular:

- Übersicht
- Allgemein
- Gastro und Ablauf
- Theater mit Zeichenfläche
- Lounge mit Zeichenfläche
- Terasse mit Zeichenfläche
- Notizen

Die Zeichenflächen speichern transparente PNG-Zeichnungen als Binary-Felder auf dem Projekt. Die Grundrisse liegen im Modul unter `static/src/img/`.

## Installation in Odoo SH

1. Ordner `gl_project_checklist` in das Custom-Addons-Repository legen.
2. Committen und nach Odoo SH pushen.
3. App-Liste aktualisieren.
4. Modul **Groundlift Projekt-Checkliste** installieren.
5. Ein Projekt öffnen. Die neuen Tabs erscheinen im Projektformular neben den bestehenden Tabs.

## Hinweise

- Die Funktion ist bewusst direkt am Projekt gespeichert und benötigt keine zusätzlichen Modelle oder Zugriffsrechte.
- Nach dem Zeichnen wird die PNG-Ebene in das Formular übernommen. Je nach Odoo-Ansicht bitte das Projekt speichern beziehungsweise den automatischen Odoo-Speichermechanismus abwarten.
- Die Schreibweise `Terasse` ist wie angefordert beibehalten.
