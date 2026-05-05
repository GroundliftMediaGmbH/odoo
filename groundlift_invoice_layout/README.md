# GROUNDLIFT Invoice Layout für Odoo 19 SH

Dieses Modul ersetzt das sichtbare `web.external_layout_wave`-Layout durch ein reduziertes GROUNDLIFT-Rechnungslayout und setzt den PDF-Dateinamen für Rechnungen/Gutschriften.

## Was das Modul ändert

1. Header des Wave-Layouts:
   - GROUNDLIFT-Logo zentriert
   - Belegnummer, Belegdatum und Liefer-/Leistungsdatum rechts
   - Seitenzählung `Seite X von Y`

2. Body des Wave-Layouts:
   - Odoo-Rechnungsinhalt bleibt erhalten
   - Wave-Hintergrund/Stripes werden entfernt
   - Tabellen werden sachlicher/ruhiger formatiert
   - doppelte rechte Infobox wird unterdrückt, weil sie im Header steht

3. Footer:
   - dreispaltiger GROUNDLIFT-Footer mit roter Linie links
   - Firmendaten, Geschäftsführung/HRB/USt-ID, Bankverbindung

4. Report-Action:
   - PDF-Name statt `Externer Bericht.pdf`, z. B. `Rechnung_RE_2026_00017.pdf`
   - Gutschriften heißen `Gutschrift_...pdf`
   - eigenes A4-Paperformat wird den Rechnungsreports zugewiesen

## Installation auf Odoo.sh

1. Den Ordner `groundlift_invoice_layout` in dein Odoo.sh-Git-Repository legen, z. B. nach:

   ```text
   /src/user/groundlift_invoice_layout
   ```

2. Committen und auf deine Odoo.sh-Branch pushen:

   ```bash
   git add groundlift_invoice_layout
   git commit -m "Add GROUNDLIFT invoice PDF layout"
   git push origin HEAD:staging/19.0
   ```

3. Warten, bis Odoo.sh die Branch neu gebaut hat.

4. In Odoo:
   - Entwicklermodus aktivieren
   - Apps öffnen
   - App-Liste aktualisieren
   - nach `GROUNDLIFT Invoice Layout` suchen
   - Modul installieren

5. Prüfen:
   - Einstellungen > Unternehmen > Dokumentenlayout konfigurieren
   - Layout muss auf `Wave` stehen, weil dieses Modul `web.external_layout_wave` überschreibt
   - eine Rechnung öffnen und neu drucken

## Wichtig bei bestehenden Rechnungen

Wenn eine Rechnung bereits als PDF-Anhang gespeichert wurde, kann Odoo je nach Report-Einstellung den alten Anhang erneut ausliefern. Dann sieht man eventuell noch den alten Dateinamen oder das alte Layout. In diesem Fall den bestehenden PDF-Anhang an der Rechnung entfernen oder den Report einmal ohne Attachment-Reload neu erzeugen.

## Anpassungspunkte

### Vertikaler Sitz von Header/Body

Datei:

```text
data/report_paperformat.xml
```

Wichtige Werte:

```xml
<field name="margin_top">42</field>
<field name="header_spacing">32</field>
```

Wenn der Body zu weit oben oder unten sitzt, zuerst diese beiden Werte feinjustieren.

### Footer-Daten

Datei:

```text
views/report_external_layout_wave.xml
```

Footer-Block suchen:

```xml
<div class="gl_footer_col">
```

Dort sind Bankverbindung, HRB und Geschäftsführung hinterlegt.

### PDF-Dateiname

Datei:

```text
models/ir_actions_report.py
```

Dort stehen `print_name_expr` und `attachment_expr`.

