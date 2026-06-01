# Groundlift Projekt-Checkliste

Odoo-19-SH-Modul für Checklisten direkt im Projektformular.

## Funktionen

- Neuer Obertab **Gastro** im Projektformular
  - Untertabs: Allgemein, Gastro und Ablauf, Theater, Lounge, Terrasse, Notizen
  - Bestehende Gastro-/Plan-/Notizfelder bleiben erhalten
  - Theater/Lounge/Terrasse weiterhin mit Zeichenfläche auf dem jeweiligen Grundriss
- Neuer Obertab **Medientechnik** im Projektformular
  - Untertabs: Audio, Video, Licht, Technischer Rundown
  - Audio/Video/Licht jeweils mit großem Notizfeld
  - Technischer Rundown als dynamische Tabelle mit Uhrzeit, ToDo und Erledigt-Checkbox
- Bestehende Datenfelder werden nicht entfernt, damit vorhandene Projektwerte bei Updates erhalten bleiben

## Installation in Odoo SH

1. Ordner `gl_project_checklist` in das Custom-Addons-Repository legen.
2. Commit + Push nach Odoo SH.
3. Apps-Liste aktualisieren.
4. Modul **Groundlift Projekt-Checkliste** installieren oder aktualisieren.

Bei einem Update bitte das Modul in Odoo aktualisieren, damit die neuen Medientechnik-Felder und das neue Rundown-Modell angelegt werden.
