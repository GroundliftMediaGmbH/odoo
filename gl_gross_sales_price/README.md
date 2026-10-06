# Groundlift Bruttopreis Eingabe – Odoo 19

Version 19.0.1.1.0

## Zweck

Das Modul ergänzt Produkte um ein editierbares Feld **Bruttopreis** und behebt
zusätzlich die Rundung des Nettopreises im Odoo-19-POS.

Beispiel bei 19 % MwSt.:

- Eingabe Bruttopreis: `3,80 €`
- exakter Nettopreis: `3,1932773109... €`
- 2 Produkte brutto: `7,60 €`

Odoo 19 rundet im Standard-POS `price_unit` über die Decimal Precision
**Product Price**. Bei zwei Nachkommastellen wird aus dem exakten Nettopreis
`3,19 €`; bei der Summen-/Steuerberechnung kann daraus `7,59 €` entstehen.

Der POS-Patch dieses Moduls erhält die volle interne Präzision **nur dann**,
wenn der Produkt-Verkaufspreis tatsächlich Nachkommastellen jenseits der
normalen Product-Price-Präzision enthält. Normale Zweidezimalpreise behalten
das Standardverhalten von Odoo.

## Upgrade von Version 19.0.1.0.0

1. Den bestehenden Modulordner `gl_gross_sales_price` durch diese Version ersetzen.
2. Commit/Push nach Odoo.sh.
3. Modul **Groundlift Bruttopreis Eingabe** aktualisieren.
4. POS vollständig neu laden (offene POS-Tabs schließen und neu öffnen; bei Bedarf Hard Reload).
5. Test: zwei verschiedene Produkte mit je 3,80 € brutto müssen zusammen 7,60 € ergeben.

Es wird bewusst **nicht** die globale Decimal Precision `Product Price`
verändert, damit andere Odoo-Bereiche nicht unnötig beeinflusst werden.
