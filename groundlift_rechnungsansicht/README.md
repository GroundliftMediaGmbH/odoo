# Groundlift Rechnungsansicht für Odoo 19 SH

Version 19.0.3.2.0

Diese Version baut auf v31 auf und behebt drei konkrete Punkte aus dem Testdruck:

1. Rechnungsnummern werden im PDF ohne Schrägstriche angezeigt, z. B. `RE_2026_00003` statt `RE/2026/00003`.
2. Die Kunden-Rechnungsadresse wird nicht mehr über das Odoo-Kontaktwidget, sondern manuell aus den Partnerfeldern gerendert. Dadurch bleibt sie auch in angepassten/übersetzten Report-Kontexten sichtbar.
3. Der Footer beginnt jetzt am linken Rand des PDF-Inhaltsbereichs. Der rote Strich sowie alle Spalten rechts davon sind auf die linke Achse von Rechnungstitel und Positionsspalte ausgerichtet.

## Dateien

- `data/cleanup_legacy_views.xml`  
  Entfernt ältere Views aus v2/v3.

- `views/report_external_layout_invoice.xml`  
  Eigenes Header-/Footer-Layout nur für GROUNDLIFT-Rechnungen. Hier sitzen Belegnummer, Belegdatum, Liefer-/Leistungsdatum, Seitenzähler und Footer.

- `views/report_invoice_templates.xml`  
  Eigener Rechnungsbody. Hier sitzen Absenderzeile, Kundenadresse, Rechnungstitel, Positionstabelle, Summen und Zahlungsbedingungen.

- `data/report_paperformat.xml`  
  Papierformat mit passenden Rändern für wiederholte Header/Footer.

- `models/ir_actions_report.py`  
  Setzt PDF-Dateiname und Paperformat für Rechnungsreports.

## Update auf Odoo.sh

```bash
cd ~/src/user
rm -rf groundlift_rechnungsansicht
unzip /pfad/zu/groundlift_rechnungsansicht_odoo19_v32.zip
git add -A groundlift_rechnungsansicht
git commit -m "Update Groundlift Rechnungsansicht invoice layout v32"
git push origin HEAD:staging/19.0
```

Danach in Odoo:

1. Odoo.sh Build abwarten, bis er grün ist.
2. Apps-Liste aktualisieren.
3. Modul **Groundlift Rechnungsansicht** aktualisieren.
4. Bereits erzeugte PDF-Anhänge an der Testrechnung löschen.
5. Rechnung neu drucken.
