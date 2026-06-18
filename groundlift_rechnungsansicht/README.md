# Groundlift Rechnungsansicht für Odoo 19 SH

Version **19.0.3.6.3**

Diese Version erweitert das bestehende Modul, ohne Modul- oder Verzeichnisnamen zu ändern.

## Änderung in Version 3.6.3

- Die **Beschreibung der Rechnung** wird im PDF jetzt als reiner Text mit
  `white-space: pre-wrap` ausgegeben, nicht mehr über `t-field`.
- Dadurch erzeugt ein normaler Zeilenumbruch per Enter denselben vertikalen
  Abstand wie ein automatischer Umbruch innerhalb einer langen Zeile.
- Zusätzliche Absatzabstände, die Odoo über Kind-Elemente oder globale Report-Styles
  einbringen könnte, werden für diesen Textblock unterdrückt.
- Alle übrigen Funktionen und Layout-Einstellungen bleiben unverändert.

## Änderung in Version 3.6.2

- Der Zeilenabstand der **Beschreibung der Rechnung** wird jetzt auch auf allen von Odoo
  innerhalb des Textfelds erzeugten Kindelementen konsequent auf **1,0** gesetzt.
- Dadurch greifen keine globalen Report-Zeilenabstände mehr in den Beschreibungstext ein.
- Alle übrigen Funktionen und Layout-Einstellungen bleiben unverändert.

## Änderung in Version 3.6.1

- Der Zeilenabstand der **Beschreibung der Rechnung** wurde auf **1,0** gesetzt.
- Alle übrigen Funktionen und Layout-Einstellungen bleiben unverändert.

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
