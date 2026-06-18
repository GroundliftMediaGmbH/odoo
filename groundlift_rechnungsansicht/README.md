# Groundlift Rechnungsansicht für Odoo 19 SH

Version **19.0.3.5.0**

Diese Version erweitert das bestehende Modul, ohne Modul- oder Verzeichnisnamen zu ändern.

## Neue Funktionen

1. Oberhalb der Tabs der Kundenrechnung stehen zwei neue Felder:
   - **Beschreibung der Rechnung**: mehrzeiliger Einleitungstext für das PDF.
   - **Zusatzangaben rechts**: optionaler mehrzeiliger Text, z. B. für Kostenstelle und PSP-Element.
2. Die Beschreibung wird im PDF oberhalb der Rechnungspositionen ausgegeben; Zeilenumbrüche bleiben erhalten.
3. Die Zusatzangaben erscheinen rechts neben der Überschrift **Rechnung** bzw. **Gutschrift** und dürfen leer bleiben.
4. Die Positionsspalte wurde verbreitert und zentriert. Links und rechts der Positionsnummer gibt es jetzt mehr Innenabstand.
5. Die Kopfzeile der Positionstabelle hat mehr vertikalen Innenabstand, damit „Pos“, „Bezeichnung“, „Menge“ usw. nicht am oberen Rand kleben.
6. Alle bisherigen Funktionen bleiben erhalten: eigenes Groundlift-Layout, Belegnummernformat, Header/Footer, Papierformat, USt.-Spalte, USt.-Summen und PDF-Dateiname.

## Technische Felder

- `account.move.groundlift_invoice_description`
- `account.move.groundlift_invoice_side_note`

## Update auf Odoo.sh

Den vorhandenen Ordner `groundlift_rechnungsansicht` im GitHub-Repository durch den gleichnamigen Ordner aus diesem ZIP ersetzen und committen.

Danach in Odoo:

1. Odoo.sh-Build abwarten.
2. Apps-Liste aktualisieren.
3. Modul **Groundlift Rechnungsansicht** aktualisieren.
4. Bei bereits gedruckten Rechnungen eventuell vorhandene alte PDF-Anhänge löschen.
5. Rechnung neu drucken.
