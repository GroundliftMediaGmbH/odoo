# Groundlift Website Color Manager für Odoo 19

Dieses Modul scannt eine gerenderte Odoo-Website im Browser und legt alle gefundenen Farben im Backend ab. Farben können pro Website überschrieben werden. Die Overrides werden über eine dynamische CSS-Route in `website.layout` geladen.

## Installation auf Odoo.sh

1. Ordner `gl_website_color_manager` in dein Odoo.sh Custom-Addons-Repository kopieren.
2. Committen und auf den passenden Branch pushen.
3. Odoo.sh Build abwarten.
4. In Odoo: Apps aktualisieren.
5. App `Groundlift Website Color Manager` installieren oder aktualisieren.

## Verwendung: ganze Seite scannen

1. Backend-Menü `Website Farben` öffnen.
2. `Homepage scannen` wählen.
3. Website und Pfad auswählen, z. B. `/`.
4. `Ganze Seite scannen` klicken. Die Website öffnet in einem neuen Tab.
5. Nach Abschluss `Alle Farben im Backend öffnen` klicken.
6. In `Farben ändern` bei einer gefundenen Farbe eine neue Hex-Farbe eintragen, z. B. `#ff6600`.
7. Die Farbe wird automatisch aktiviert und im Frontend als CSS-Override geladen.

## Verwendung: Bereich direkt anklicken

1. Backend-Menü `Website Farben` öffnen.
2. `Homepage scannen` wählen.
3. Website und Pfad auswählen.
4. `Bereich anklicken` klicken.
5. Auf der Website wird ein gelber Auswahlrahmen angezeigt.
6. Den gewünschten Bereich oder Button/Textblock einmal anklicken.
7. Das Modul speichert nur die Farben dieses Bereichs und zeigt Links an:
   - `Angeklickte Farben direkt bearbeiten`
   - `Auswahl-Scan öffnen`
   - `Alle Farben im Backend öffnen`
8. In der geöffneten Liste kannst du direkt `Neue Farbe` setzen und `Override aktiv` einschalten.

Der normale Scan zeigt nach Abschluss ebenfalls einen Button `Bereich auf der Seite anklicken`, damit du nach dem Gesamtscan direkt einzelne Bereiche auswählen kannst.

## Hinweise

- Der Scanner läuft nur mit URL-Parameter `?gl_color_scan=1`.
- Die direkte Bereichsauswahl läuft zusätzlich mit `&gl_color_pick=1` oder über den Button im Scan-Overlay.
- Speichern dürfen nur Systemnutzer oder Website-Designer.
- Erfasst werden gerenderte Styles, CSS-Variablen, SVG `fill`/`stroke`, Schatten und Gradients.
- Pseudo-States wie `:hover` werden zusätzlich aus zugänglichen Stylesheets gelesen, soweit der Browser Zugriff auf `document.styleSheets` erlaubt.
- Einzelne Fundstellen können deaktiviert werden, wenn ein Override zu breit greift.
