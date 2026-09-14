# Groundlift To-Do Categories – Odoo 19 SH

Version 19.0.1.2.0

Erweitert die native Odoo-19-App **To-Do** um gemeinsame Kategorien, eine linke Kategorienauswahl und Team-/Meine-To-Dos-Ansichten.

## Unkategorisiert

- Die Systemkategorie **Unkategorisiert** wird automatisch angelegt.
- Beim Installieren oder Upgrade werden alle vorhandenen obersten privaten To-Dos ohne Kategorie automatisch dieser Kategorie zugeordnet.
- Neue To-Dos ohne gewählte Kategorie landen automatisch in **Unkategorisiert**.
- Wird die Kategorie eines To-Dos geleert, wird automatisch wieder **Unkategorisiert** gesetzt.
- Die Systemkategorie kann nicht gelöscht, umbenannt oder archiviert werden.
- Wird eine andere Kategorie gelöscht, fallen die darin enthaltenen To-Dos automatisch auf **Unkategorisiert** zurück.


## Version 19.0.1.3.0

- Repariert bestehende private To-Dos mit Benutzerzuweisung, aber fehlender persönlicher Phase.
- Solche Datensätze werden beim Upgrade über Odoos native `_populate_missing_personal_stages()`-Logik in die erste persönliche Phase verschoben (standardmäßig „Eingang“).
- Neu erstellte oder neu zugewiesene private To-Dos werden ebenfalls automatisch auf fehlende Phasen geprüft.
