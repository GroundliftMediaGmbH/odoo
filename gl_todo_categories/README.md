# Groundlift To-Do Categories – Odoo 19 SH

Version 19.0.1.4.0

## Neu in 1.4

- Die rechte Kanban-Seite verwendet jetzt eine **gemeinsame, gespeicherte To-Do-Phase** statt Odoos benutzerabhängiger `personal_stage_type_id`.
- Dadurch gibt es in „Alle To-Dos“ und bei unzugewiesenen To-Dos keine technisch leere Spalte **„Keine“** mehr.
- Unzugewiesene To-Dos bleiben wirklich unzugewiesen und landen zwingend in der Kategorie **„Unkategorisiert“**.
- Unzugewiesene bzw. phasenlose Altbestände starten rechts in **„Eingang“**.
- Vorhandene persönliche Odoo-Phasen werden beim Upgrade bestmöglich auf die gemeinsamen Phasen abgebildet.
- Änderungen der gemeinsamen Phase werden für zugewiesene Mitarbeiter in die nativen persönlichen Odoo-Phasen gespiegelt.
- Kategorien bleiben links im Search Panel auswählbar.

## Upgrade

Bestehenden Ordner `gl_todo_categories` vollständig ersetzen, pushen und anschließend das Modul in Odoo upgraden.
