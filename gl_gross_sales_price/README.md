# Groundlift Bruttopreis Eingabe – Odoo 19
Version **19.0.1.7.0**

## v1.7.0 – Eventticket 12,00 EUR statt 11,99 EUR

Diagnose am realen Ticket:
- ticket.price: 11.214953
- Steuer: 7 %
- Firma verwendet `round_per_line`
- Odoo-Core `event_product` berechnet `price_incl` / `price_reduce_taxinc`
  mit `tax_ids.compute_all(...)`.

Bei `round_per_line` kann die Basis zuerst auf Cent reduziert werden:
- 11.214953 -> 11.21
- 7 % von 11.21 -> 0.78
- Brutto -> 11.99

Die mathematisch beabsichtigte Berechnung lautet:
- 11.214953 * 1.07 = 11.99999971
- Endbetrag auf Währung runden -> 12.00

### Fix

1. `event.event.ticket.price_incl`
2. `event.event.ticket.price_reduce_taxinc`

werden mit voller Basispräzision berechnet und erst das Endergebnis auf die
Währung gerundet.

Zusätzlich werden `sale.order.line`-Positionen mit `event_ticket_id` für die
Steuerberechnung als "total included" behandelt. Damit bleibt der auf der
Eventseite angezeigte Bruttopreis auch im Groundlift-Checkout und Auftrag
führend.

Normale Verkaufspositionen und POS-Positionen sind davon nicht betroffen.

Die verworfene v1.3-POS-Steuerlogik und die v1.6-Ticketpreis-Umschreibung sind
nicht enthalten. Basis ist der stabile v1.5-Code.
