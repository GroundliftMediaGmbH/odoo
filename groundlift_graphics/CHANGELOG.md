## 19.0.1.0.2

- Behebt die SCSS-Kompilierung in Odoo: `width: min(100%, 1420px)` wurde durch `width: 100%` plus `max-width: 1420px` ersetzt. Ältere Sass-Compiler interpretieren CSS-`min()` als Sass-Funktion und brechen bei gemischten Einheiten `%` und `px` ab.

# Changelog

## 19.0.1.0.1

- Odoo-19-Kompatibilität der Suchansicht korrigiert: Das `group`-Element in Suchansichten wird nun ohne die nicht zulässigen Attribute `string` und `expand` verwendet.

## 19.0.1.0.0

- Erste Version für Odoo 19 SH
- Event-Integration und Grafikdatensatz
- Owl/Canvas-Grafikeditor
- Polygonaler Bildausschnitt mit Crop-, Dreh-, Verschiebe- und Zoomsteuerung
- Automatische Farbpalette und Kontrastmodus
- Dynamische Texte, Logo, Rahmen, Störer, QR-Code und PNG-Ausgabe
