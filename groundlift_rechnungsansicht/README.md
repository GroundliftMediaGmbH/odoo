# Groundlift Rechnungsansicht – Odoo 19 SH

Dieses Modul ersetzt den sichtbaren Rechnungsreport gezielt für `account.report_invoice_document` und verwendet ein eigenes GROUNDLIFT-External-Layout nur für Rechnungen. Es überschreibt nicht mehr global `web.external_layout_wave`.

## Enthaltene Fixes v3

1. Senderzeile unter dem Logo kleiner und rot.
2. Kundenadresse kleiner.
3. Belegnummer, Belegdatum und Liefer-/Leistungsdatum rechts auf Höhe der Anschrift.
4. Seitenzähler darunter mit Abstand: `Seite x von y`.
5. Titel links: `Rechnung [Rechnungsnummer]`.
6. Horizontale Tabellenlinie im finalen Rechnungsbody, nicht nur in der Layout-Vorschau.
7. Footer-CSS direkt im Footer, damit wkhtmltopdf die Spalten im finalen PDF korrekt rendert.

## Dateien

- `views/report_external_layout_invoice.xml`  
  Eigenes Header-/Footer-Layout nur für Rechnungen.

- `views/report_invoice_document.xml`  
  Ersetzt den sichtbaren Rechnungsbody inklusive Adressblock, Titel, Positions-Tabelle und Summenblock.

- `views/report_invoice_language.xml`  
  Erzwingt Deutsch für den Rechnungsreport.

- `data/report_paperformat.xml`  
  A4-Papierformat mit ausreichendem Kopf-/Fußbereich für mehrseitige Rechnungen.

- `data/report_action_setup.xml` und `models/ir_actions_report.py`  
  Setzt PDF-Dateiname und Papierformat auf den Rechnungsreport.

## Installation auf Odoo.sh

```bash
cd ~/src/user
unzip /pfad/zu/groundlift_rechnungsansicht_odoo19_v3.zip
# Falls der Ordner schon existiert, ersetze ihn komplett:
# rm -rf groundlift_rechnungsansicht
# unzip /pfad/zu/groundlift_rechnungsansicht_odoo19_v3.zip

git add groundlift_rechnungsansicht
git commit -m "Update Groundlift Rechnungsansicht invoice layout v3"
git push origin HEAD:staging/19.0
```

Danach in Odoo:

1. Entwicklermodus aktivieren.
2. Apps > App-Liste aktualisieren.
3. Modul `Groundlift Rechnungsansicht` suchen.
4. Falls schon installiert: `Upgrade/Aktualisieren` klicken.
5. Neue Testrechnung drucken.

## Wichtig

Wenn Odoo einen alten PDF-Anhang wiederverwendet, den alten Anhang an der Rechnung löschen und die Rechnung erneut drucken.
