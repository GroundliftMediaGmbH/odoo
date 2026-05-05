# Groundlift Rechnungsansicht für Odoo 19 SH

Version 19.0.3.1.0

Diese Version ersetzt nicht mehr `web.external_layout_wave` global. Stattdessen wird im Standard-Wrapper `account.report_invoice` nur der Aufruf des Rechnungsdokuments für Kundenrechnungen/Gutschriften durch ein eigenes GROUNDLIFT-Rechnungsdokument ersetzt.

## Fix gegenüber v3

Der Fehler

`Element <xpath expr="//t[@t-call='web.external_layout']"> kann nicht ... lokalisiert werden`

kam daher, dass v3 direkt in `account.report_invoice_document` nach `web.external_layout` gesucht hat. Auf der konkreten Odoo.sh-Datenbank ist dieses innere Template offenbar bereits anders erweitert oder aufgelöst. Diese Version patcht deshalb den stabileren äußeren Wrapper `account.report_invoice`.

## Dateien

- `data/cleanup_legacy_views.xml`  
  Entfernt ältere Views aus v2/v3, insbesondere den globalen Wave-Override.

- `views/report_external_layout_invoice.xml`  
  Eigenes Header-/Footer-Layout nur für die GROUNDLIFT-Rechnung.

- `views/report_invoice_templates.xml`  
  Eigener Rechnungsbody und Replacement des Dokument-Aufrufs in `account.report_invoice`.

- `data/report_paperformat.xml`  
  Papierformat mit Rändern für wiederholte Header/Footer.

- `models/ir_actions_report.py`  
  Setzt PDF-Dateinamen und Paperformat für Rechnungsreports.

## Update auf Odoo.sh

```bash
cd ~/src/user
rm -rf groundlift_rechnungsansicht
unzip /pfad/zu/groundlift_rechnungsansicht_odoo19_v31.zip
git add -A groundlift_rechnungsansicht
git commit -m "Fix Groundlift Rechnungsansicht invoice report inheritance"
git push origin HEAD:staging/19.0
```

Danach in Odoo:

1. Apps-Liste aktualisieren.
2. Modul **Groundlift Rechnungsansicht** aktualisieren.
3. Bereits erzeugte PDF-Anhänge an der Testrechnung löschen.
4. Rechnung erneut drucken.
