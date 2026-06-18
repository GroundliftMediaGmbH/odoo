# Groundlift Rechnungsansicht für Odoo 19 SH

Version **19.0.3.6.0**

Diese Version erweitert das bestehende Modul, ohne Modul- oder Verzeichnisnamen zu ändern.

## Änderungen in Version 3.6

1. **Zusatzangaben rechts** beginnen im PDF auf derselben Höhe wie die Überschrift
   **Rechnung / Gutschrift** und die Belegnummer.
2. Der Zeilenabstand des rechten Zusatzblocks wurde auf **1,0** gesetzt.
3. Rechnungspositionen unterstützen jetzt vollständig:
   - **Abschnitte** (`line_section`)
   - **Unterabschnitte** (`line_subsection`, neu in Odoo 19)
   - **Notizen** (`line_note`)
4. Fehlen Abschnitts- oder Notizzeilen auf der erzeugten Rechnung, obwohl die
   Produktpositionen mit einem Angebot/Auftrag verknüpft sind, rekonstruiert der
   PDF-Bericht die fehlenden Anzeigezeilen aus dem verknüpften Angebot. Dabei werden
   ausschließlich Überschriften und Notizen ergänzt. Mengen, Preise, Steuern und
   Summen stammen weiterhin unverändert aus den tatsächlichen Rechnungszeilen.
5. Bereits vorhandene manuelle Rechnungszeilen bleiben erhalten und werden weiterhin
   anhand ihrer Rechnungsreihenfolge ausgegeben.

## Bereits enthaltene Funktionen

- **Beschreibung der Rechnung** als mehrzeiliger Einleitungstext oberhalb der Positionen.
- **Zusatzangaben rechts** für Kostenstelle, PSP-Element und ähnliche Angaben.
- Eigenes Groundlift-Layout mit Header, Footer und Papierformat.
- Groundlift-Belegnummernformat und passender PDF-Dateiname.
- USt.-Satz je Position und getrennte USt.-Summen je Steuersatz.
- Verbreiterte und zentrierte Positionsspalte sowie optimierte Tabellenkopf-Abstände.

## Technische Felder

- `account.move.groundlift_invoice_description`
- `account.move.groundlift_invoice_side_note`

## Abhängigkeiten

- `account`
- `sale`
- `web`

Die Abhängigkeit `sale` wird benötigt, damit fehlende Abschnitte, Unterabschnitte und
Notizen zuverlässig aus dem zugehörigen Angebot/Auftrag übernommen werden können.

## Update auf Odoo.sh

Den vorhandenen Ordner `groundlift_rechnungsansicht` im GitHub-Repository durch den
gleichnamigen Ordner aus diesem ZIP ersetzen und committen.

Danach in Odoo:

1. Odoo.sh-Build abwarten.
2. Apps-Liste aktualisieren.
3. Modul **Groundlift Rechnungsansicht** aktualisieren.
4. Bei bereits gedruckten Rechnungen eventuell vorhandene alte PDF-Anhänge löschen.
5. Rechnung neu drucken.
