# Groundlift Bruttopreis Eingabe – Odoo 19
Version **19.0.1.8.0**

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

## v1.8.0 – Produkt-Bruttopreis / POS (3,60 statt 3,61 EUR)

- Beide Umrechnungen im Produktstamm verwenden explizit
  `rounding_method="round_globally"` und `round_base=False`, unabhängig
  von der Steuerrundungsmethode der Firma. Brutto wird erst am Ende auf
  die Währungsgenauigkeit gerundet; Netto bleibt ungerundet.
- Upgrade-Migration: Nur explizit bruttopreisgesteuerte Produkte werden
  anhand ihres gespeicherten Bruttos neu berechnet (auch archivierte).
  Bei gemeinsamen Produkten mit widersprüchlichen Steuerergebnissen
  mehrerer Firmen wird die Änderung übersprungen und im Log gemeldet.
  Normale Produkte, Bruttopreise, Tickets und vorhandene Aufträge werden
  von dieser Migration nicht umgeschrieben.
- Der POS-Patch erhält die Netto-Präzision für gesteuerte Produkte;
  für andere Produkte wird die originale Odoo-Methode aufgerufen.
- Keine Änderung der Firmen-/Währungsrundung. Für reguläre POS-Verkäufe
  mit Nettosteuern weiterhin globale Steuerrundung und Product Price = 6
  empfohlen. Preislisten, Steuermappings und Varianten können den
  tatsächlich verkauften Preis absichtlich ändern.

Nach Upgrade POS neu laden (neuer Warenkorb) und 1, 2, 3, 10 Stück
zu 3,60 EUR testen: 3,60 / 7,20 / 10,80 / 36,00 EUR. Kassenbon und
gespeicherten Auftrag kontrollieren. Odoo-Integrationstest auf Staging
notwendig; lokale Syntax-/Modultests ersetzen diesen nicht.
