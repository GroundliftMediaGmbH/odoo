# Groundlift Website Color Manager für Odoo 19

Dieses Modul scannt eine gerenderte Odoo-Website im Browser und legt alle gefundenen Farben im Backend ab. Farben können pro Website überschrieben werden. Die Overrides werden über eine dynamische CSS-Route in `website.layout` geladen.

## Installation auf Odoo.sh

1. Ordner `gl_website_color_manager` in dein Odoo.sh Custom-Addons-Repository kopieren.
2. Committen und auf den passenden Branch pushen.
3. Odoo.sh Build abwarten.
4. In Odoo: Apps aktualisieren.
5. App `Groundlift Website Color Manager` installieren.

## Verwendung

1. Backend-Menü `Website Farben` öffnen.
2. `Homepage scannen` wählen.
3. Website und Pfad auswählen, z. B. `/`.
4. `Scan starten` klicken. Die Website öffnet in einem neuen Tab.
5. Nach Abschluss `Farben im Backend öffnen` klicken.
6. In `Farben ändern` bei einer gefundenen Farbe eine neue Hex-Farbe eintragen, z. B. `#ff6600`.
7. Die Farbe wird automatisch aktiviert und im Frontend als CSS-Override geladen.

## Hinweise

- Der Scanner läuft nur mit URL-Parameter `?gl_color_scan=1`.
- Speichern dürfen nur Systemnutzer oder Website-Designer.
- Erfasst werden gerenderte Styles, CSS-Variablen, SVG `fill`/`stroke`, Schatten und Gradients.
- Pseudo-States wie `:hover` werden zusätzlich aus zugänglichen Stylesheets gelesen, soweit der Browser Zugriff auf `document.styleSheets` erlaubt.
- Einzelne Fundstellen können deaktiviert werden, wenn ein Override zu breit greift.
