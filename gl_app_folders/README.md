# Groundlift App-Folders Desktop für Odoo 19

Persönlicher Odoo Desktop mit App-Ordnern wie bei Android.

## Funktionen

- Benutzerindividuelle Ordner für Odoo Apps
- Ordner mit eigener Bezeichnung und eigenem Icon
- Apps per Drag & Drop in Ordner verschieben
- App auf App ziehen, um direkt einen neuen Ordner zu erzeugen
- Ordner öffnen, bearbeiten, löschen und Apps wieder entfernen
- Button zum Setzen dieses Desktops als persönliche Startseite

## Version 19.0.1.0.3

Diese Version behebt den CSS/SCSS-Asset-Fehler in Odoo 19:

- Die SCSS-Datei wurde durch eine plain CSS-Datei ersetzt.
- Sass-problematische CSS-Funktionen wie `min()` und `color-mix()` wurden entfernt.
- Verschachtelte SCSS-Regeln wurden in normales CSS umgewandelt.

Damit wird der globale Backend-Asset-Build nicht mehr durch den Style des Moduls blockiert.

## Installation auf Odoo.sh

1. Modulordner `gl_app_folders` in das Custom-Addons-Repository legen.
2. Commit + Push auf den gewünschten Odoo.sh-Branch.
3. Build abwarten.
4. In Odoo die App-Liste aktualisieren.
5. Modul installieren oder aktualisieren.
6. Danach Browser-Cache leeren bzw. Odoo mit `?debug=assets` prüfen, falls alte Asset-Bundles gecacht sind.


## Design-Update in 19.0.1.0.3

- Dunkle, zur Odoo-Navigation passende Desktop-Oberfläche
- Überarbeitete Ordnerkarten im moderneren Android-/Launcher-Stil
- Dunkler Dialog für geöffnete Ordner
- Bessere Lesbarkeit für Überschrift, Suche und Kacheln
