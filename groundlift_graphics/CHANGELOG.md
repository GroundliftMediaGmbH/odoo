# Changelog

## 19.0.1.3.5

- Macht den Canvas-Renderer fehlertolerant: Ein defektes/ungeladenes Veranstaltungsbild, QR-Bild oder Overlay stoppt nicht mehr alle weiteren Ebenen. Dadurch werden Logos, Rahmen, Störer, Textmasken und Getränkekarten weiterhin gezeichnet.
- Lädt Template-Assets mit URL-kodierten Dateinamen, damit Ordner/Dateien mit Leerzeichen oder Umlauten zuverlässig funktionieren.
- Ergänzt Cache-Busting für den isolierten Editor und das Standalone-JavaScript, damit Odoo.sh/Browser nicht versehentlich die alte fehlerhafte JS-Datei weiterverwenden.
- Stabilisiert den JPG-/ZIP-Export, weil `renderAllOutputs()` nicht mehr an einer einzelnen fehlerhaften Ebene scheitert.

## 19.0.1.3.4

- Behebt den Canvas-Renderabbruch nach der Verlaufsebene: Die Bildrotation verwendet nun die tatsächlich übergebene Bildtransformation statt einer nicht vorhandenen Variant-Variable.
- Feste sichtbare Ebenen für Claim, externe Logos und die Sudhaus-Getränkekarte werden wieder in der korrekten Ebenenreihenfolge gerendert.

## 19.0.1.1.0

- Multi-Format-Editor auf Basis aller gelieferten PNG-Vorlagen ergänzt (Kino, Plakat, Social, Foyer, Stream, Sudhaus Main usw.).
- Ein Bild kann jetzt für mehrere Ausspielformate verwendet und pro Format separat justiert werden.
- Automatische Vorausfüllung der Übersichtstexte erweitert, inkl. Kurzzusammenfassung und Kategorie-Label.
- Download der aktuellen Ausgabe als JPG sowie aller gespeicherten Ausgaben als ZIP ergänzt.
- Einfaches Getränkekarten-Setup mit speicherbaren Profilen und Odoo-Produkten ergänzt.

## 19.0.1.0.4

- Unter der Uhrzeit wird nun bevorzugt der Wert aus dem Event-Feld mit dem Anzeigenamen `Kategorie (Label)` verwendet (Groundlift-Website-Tab).
- Fallbacks bleiben erhalten: Wenn kein solches Feld vorhanden oder befüllt ist, verwendet die App weiterhin Eventtyp bzw. Tag.

## 19.0.1.0.3

- Korrigiert die Größe von `Kino_Logo.png`, `Kino_Rahmen.png` und `Kino_Stoerer.png`: Die sichtbaren Alpha-Bereiche werden unabhängig von einer Odoo-seitigen Skalierung der transparenten Gesamtfläche auf die Referenzkoordinaten gesetzt.
- Export auf JPG mit 96 % Qualität umgestellt.
- Automatische Dateinamen im Schema `Erstelldatum-Veranstaltungsdatum Veranstaltungsname_Ausspielformat.jpg`.
- Der Suffix des Ausspielformats ist in der Grafikvorlage konfigurierbar; Standard ist `Kino`.
- Bestehende ältere `.png`-Dateinamen werden beim nächsten Öffnen des Editors automatisch durch den neuen Vorschlag ersetzt.

## 19.0.1.0.2

- Behebt die SCSS-Kompilierung in Odoo: `width: min(100%, 1420px)` wurde durch `width: 100%` plus `max-width: 1420px` ersetzt. Ältere Sass-Compiler interpretieren CSS-`min()` als Sass-Funktion und brechen bei gemischten Einheiten `%` und `px` ab.

## 19.0.1.0.1

- Odoo-19-Kompatibilität der Suchansicht korrigiert: Das `group`-Element in Suchansichten wird nun ohne die nicht zulässigen Attribute `string` und `expand` verwendet.

## 19.0.1.0.0

- Erste Version für Odoo 19 SH
- Event-Integration und Grafikdatensatz
- Owl/Canvas-Grafikeditor
- Polygonaler Bildausschnitt mit Crop-, Dreh-, Verschiebe- und Zoomsteuerung
- Automatische Farbpalette und Kontrastmodus
- Dynamische Texte, Logo, Rahmen, Störer, QR-Code und PNG-Ausgabe
