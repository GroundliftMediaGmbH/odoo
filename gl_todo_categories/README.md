# Groundlift To-Do Categories – Odoo 19 SH

Version 19.0.1.4.1

## Fix 1.4.1

- Entfernt den Registry-kritischen Default vom neuen Feld `gl_todo_phase_id`.
- Die gemeinsamen Phasen werden erst nach vollständigem Modell-/Schemaaufbau erzeugt.
- Bestehende private To-Dos werden danach migriert.
- Normale Projektaufgaben erhalten keine Groundlift-To-Do-Phase.
- Unzugewiesene private To-Dos werden weiterhin zwingend `Unkategorisiert` und beginnen in `Eingang`.
- Kategorien links und gemeinsame Phasen rechts bleiben erhalten.

Bestehenden Ordner `gl_todo_categories` vollständig ersetzen, pushen und das Modul upgraden.
