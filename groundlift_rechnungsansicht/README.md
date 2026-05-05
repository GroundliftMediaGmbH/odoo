# Groundlift Rechnungsansicht für Odoo 19 SH

Version 19.0.3.3.0

Diese Version baut auf v32 auf und behebt vier konkrete Punkte aus dem Testdruck:

1. Rechnungsnummern werden im PDF im Format `RE202600003` angezeigt, also ohne Schrägstriche und mit fünfstelliger laufender Nummer.
2. Die Kunden-Rechnungsadresse aus `partner_id` wird links im Header auf Höhe der Belegnummer manuell aus den Partnerfeldern gerendert.
3. Oberhalb von Kundenadresse und Belegnummer steht die rote Absenderzeile `Groundlift Media GmbH · Am Eichet 11 a · 86938 Schondorf`.
4. Unterhalb der Tabellenüberschrift `Pos` bis `Betrag EUR` wird eine dünne horizontale Trennlinie gerendert.

## Dateien

- `data/cleanup_legacy_views.xml`  
  Entfernt ältere Views aus v2/v3.

- `views/report_external_layout_invoice.xml`  
  Eigenes Header-/Footer-Layout nur für GROUNDLIFT-Rechnungen. Hier sitzen Belegnummer, Belegdatum, Liefer-/Leistungsdatum, Seitenzähler und Footer.

- `views/report_invoice_templates.xml`  
  Eigener Rechnungsbody. Hier sitzen Absenderzeile, Kundenadresse, Rechnungstitel, Positionstabelle, Summen und Zahlungsbedingungen.

- `data/report_paperformat.xml`  
  Papierformat mit passenden Rändern für wiederholte Header/Footer.

- `models/account_move.py`  
  Formatiert die sichtbare Rechnungsnummer für PDF und Dateiname.

- `models/ir_actions_report.py`  
  Setzt PDF-Dateiname und Paperformat für Rechnungsreports.

## Update auf Odoo.sh

```bash
cd ~/src/user
rm -rf groundlift_rechnungsansicht
unzip /pfad/zu/groundlift_rechnungsansicht_odoo19_v33.zip
git add -A groundlift_rechnungsansicht
git commit -m "Update Groundlift Rechnungsansicht invoice layout v33"
git push origin HEAD:staging/19.0
```

Danach in Odoo:

1. Odoo.sh Build abwarten, bis er grün ist.
2. Apps-Liste aktualisieren.
3. Modul **Groundlift Rechnungsansicht** aktualisieren.
4. Bereits erzeugte PDF-Anhänge an der Testrechnung löschen.
5. Rechnung neu drucken.
