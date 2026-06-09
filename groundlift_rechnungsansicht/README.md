# Groundlift Rechnungsansicht für Odoo 19 SH

Version 19.0.3.4.0

Diese Version ergänzt die bestehende Groundlift-Rechnungsansicht um die gewünschte USt.-Darstellung:

1. Die Positionstabelle enthält eine zusätzliche Spalte **USt. %**.
2. Der angezeigte Steuersatz kommt aus den tatsächlich auf der Rechnungszeile gesetzten Odoo-Steuern (`account.move.line.tax_ids`). Diese werden in Odoo aus Produktsteuer und ggf. Steuerzuordnung/Fiscal Position erzeugt.
3. Im Summenbereich wird die Umsatzsteuer je verwendetem USt.-Satz getrennt ausgewiesen, z. B.:
   - `Umsatzsteuer 7,00 % (aus 700,00 € netto)`
   - `Umsatzsteuer 19,00 % (aus 610,00 € netto)`
4. Auch Rechnungen mit 0,00 % USt. zeigen eine eigene 0,00-%-Zeile im Summenbereich.
5. Bestehende Funktionen bleiben erhalten: eigenes Groundlift-Layout, Belegnummernformat, Header/Footer, Paperformat und PDF-Dateiname.

## Dateien

- `data/cleanup_legacy_views.xml`  
  Entfernt ältere Views aus vorherigen Modulversionen.

- `views/report_external_layout_invoice.xml`  
  Eigenes Header-/Footer-Layout nur für GROUNDLIFT-Rechnungen.

- `views/report_invoice_templates.xml`  
  Eigener Rechnungsbody mit Positionstabelle, USt.-Spalte, USt.-Summen je Steuersatz und Zahlungsbedingungen.

- `data/report_paperformat.xml`  
  Papierformat mit passenden Rändern für wiederholte Header/Footer.

- `models/account_move.py`  
  Formatiert die sichtbare Rechnungsnummer und liefert USt.-Satz je Position sowie USt.-Summen je Steuersatz.

- `models/ir_actions_report.py`  
  Setzt PDF-Dateiname und Paperformat für Rechnungsreports.

## Update auf Odoo.sh

```bash
cd ~/src/user
rm -rf groundlift_rechnungsansicht
unzip /pfad/zu/groundlift_rechnungsansicht_odoo19_v34.zip
git add -A groundlift_rechnungsansicht
git commit -m "Update Groundlift Rechnungsansicht VAT breakdown v34"
git push origin HEAD:staging/19.0
```

Danach in Odoo:

1. Odoo.sh Build abwarten, bis er grün ist.
2. Apps-Liste aktualisieren.
3. Modul **Groundlift Rechnungsansicht** aktualisieren.
4. Bereits erzeugte PDF-Anhänge an der Testrechnung löschen, sonst zeigt Odoo eventuell noch das alte PDF.
5. Rechnung neu drucken.
