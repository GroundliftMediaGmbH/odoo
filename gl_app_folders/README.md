# Groundlift App-Folders Desktop für Odoo 19

Persönlicher Odoo Desktop mit App-Ordnern wie bei Android.

## Funktionen

- Benutzerindividuelle Ordner für Odoo Apps
- Ordner mit eigener Bezeichnung und eigenem Icon
- Apps per Drag & Drop in Ordner verschieben
- App auf App ziehen, um direkt einen neuen Ordner zu erzeugen
- Ordner öffnen, bearbeiten, löschen und Apps wieder entfernen
- Button zum Setzen dieses Desktops als persönliche Startseite

## Version 19.0.1.2.0

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


## Premium-Update in 19.0.1.1.0

- Farbige Ordner-Cover mit echter Farbauswahl
- Eigenes Bearbeiten-Modal statt Browser-Prompts
- Drag-&-Drop-Neusortierung der Ordner auf dem Desktop
- Optionaler gläserner Dark-Look per Schalter
- Aufgeräumtere Ordnerkarten: Bezeichnung unten, ohne zusätzliches Ordner-Icon/Count im Kachelkopf
- Geöffnete Ordner ohne großes Titel-Icon


## Hover-Orbit-Update in 19.0.1.2.0

- Ordner zeigen bei Hover direkt anklickbare App-Orbits um die Kachel
- Glas-Look ist jetzt standardmäßig aktiv, ohne Umschalter
- Desktop-Überschrift entfernt
- Scrollbarer Desktop bei vielen Apps/Ordnern


## Version 19.0.1.2.1

Präzisionsfixes:

- App-Icons mit vorhandenem Bild werden ohne zusätzliche Platzhalterfläche angezeigt.
- Apps ohne eigenes Icon behalten die Platzhalterfläche.
- Der linke obere Odoo-Home-/App-Button öffnet aus normalen Apps heraus den persönlichen „Mein Desktop“. Befindet man sich bereits in „Mein Desktop“, bleibt Odoos Standardverhalten erhalten.
- Hover-Orbit-Apps zeigen unterhalb des Icons den Appnamen in kleiner Schrift.


## Version 19.0.1.2.2

Scroll-Fix:

- „Mein Desktop“ ist jetzt eine eigene Scrollfläche innerhalb der Odoo-Client-Action.
- Auch bei vielen Apps/Ordnern sind unten liegende Einträge erreichbar.
- Zusätzlicher unterer Innenabstand verhindert, dass die letzte App-Reihe am Bildschirmrand klebt.


## Version 19.0.1.2.3

Tastatur-Suche:

- In „Mein Desktop“ kann direkt getippt werden, ohne vorher das Suchfeld anzuklicken.
- Der erste getippte Buchstabe wird sofort in die Suche übernommen.
- Backspace und Escape funktionieren außerhalb von Eingabefeldern ebenfalls sinnvoll für die Suche.
- Während Ordner- oder Bearbeiten-Dialoge geöffnet sind, werden Tastatureingaben nicht abgefangen.
