# GROUNDLIFT Invoice Layout für Odoo 19 SH

Version 19.0.1.1.0

Dieses Modul passt das Odoo-Layout `web.external_layout_wave` an das reduzierte GROUNDLIFT-Rechnungslayout an und setzt den Dateinamen der Rechnungs-PDFs.

## Was in dieser Version angepasst wurde

1. **Horizontale Linien**
   - Linien unter der Positionstabelle werden nun direkt auf `thead th` gesetzt, weil wkhtmltopdf `border-bottom` auf `tr` häufig nicht zuverlässig rendert.
   - Summenbereiche erhalten eine dezente obere Trennlinie.

2. **Schriftgrößen**
   - Body, Tabellen, Summen und Header wurden deutlich kleiner gesetzt.
   - Der Dokumenttitel wird nicht mehr in Odoo-Primärfarbe, sondern neutral schwarz gerendert.

3. **Deutsche Begriffe**
   - Das Modul zwingt den Rechnungsreport auf `de_DE`.
   - Voraussetzung: Deutsch ist in Odoo aktiv.
   - Maßeinheiten wie `Units` oder `Hours` kommen aus den Maßeinheiten-Datensätzen. Wenn diese trotzdem englisch bleiben, müssen die Maßeinheiten in Odoo übersetzt/umbenannt werden.

4. **Footer**
   - Der Footer nutzt jetzt absolute Spaltenpositionen statt `display: table-cell`, weil wkhtmltopdf Tabellen im Footer unzuverlässig umbrechen kann.
   - Die Spalten sind breiter und näher am Referenzlayout.

5. **Papierformat**
   - Der obere Rand wurde vergrößert, damit Inhalt auf Folgeseiten nicht in Logo/Belegdaten/Seitenzahl läuft.

## Installation / Update auf Odoo.sh

Den Ordner `groundlift_invoice_layout` in `/src/user` legen und dann:

```bash
git add groundlift_invoice_layout
git commit -m "Refine GROUNDLIFT invoice PDF layout"
git push origin HEAD:staging/19.0
```

Danach in Odoo:

1. Apps-Liste aktualisieren.
2. Modul `GROUNDLIFT Invoice Layout` aktualisieren.
3. Rechnung neu drucken.

Bei bereits erzeugten Rechnungs-PDFs ggf. den alten PDF-Anhang an der Rechnung löschen, damit Odoo das PDF neu rendert.

## Wichtige Dateien

- `views/report_external_layout_wave.xml`  
  Header, Body-CSS, Tabellenlinien, Schriftgrößen, Footer.

- `views/report_invoice_language.xml`  
  Erzwingt deutsche Rechnungsbegriffe über `t-lang = 'de_DE'`.

- `data/report_paperformat.xml`  
  A4-Ränder und Header-Abstände.

- `models/ir_actions_report.py`  
  PDF-Dateiname für Rechnungen/Gutschriften.
