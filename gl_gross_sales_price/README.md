# Groundlift Bruttopreis Eingabe – Odoo 19
Version **19.0.1.6.0**

## v1.6.0 – Event-Ticket 12,00 → 11,99 Fix

Odoo hält den Preis eines Eventtickets (`event.event.ticket.price`) netto.
Der Website-/Checkout-Bruttopreis wird anschließend aus diesem Netto plus
Produktsteuer berechnet.

Bei einem gewünschten Bruttopreis von 12,00 EUR und 7 % MwSt. lautet der
exakte Nettowert:

    12.00 / 1.07 = 11.214953271...

Wird dieser Wert irgendwo auf 11,21 EUR reduziert, ergibt die erneute
Bruttoberechnung:

    11.21 * 1.07 = 11.9947 -> 11.99 EUR

v1.6 schützt genau gegen diesen Präzisionsverlust.

### Was der Fix macht

- Nur Tickets, deren verknüpftes Produkt ausdrücklich
  `gl_gross_price_managed = True` ist, werden berücksichtigt.
- Wenn ein Ticket-Netto exakt der auf Währungsstellen gerundeten Form des
  korrekten Produkt-Nettos entspricht, wird wieder der exakte Netto-Wert
  gespeichert.
- Echte, abweichende manuelle Ticketpreise werden nicht verändert.
- Beim Upgrade werden bereits betroffene Tickets nach demselben konservativen
  Kriterium repariert.
- POS-Logik bleibt auf dem stabilen v1.5/v1.4/v1.2-Pfad.
- Die verworfene v1.3-Steuer-Summenlogik ist nicht enthalten.

### Beispiel

Produkt:
- Bruttopreis 12,00 EUR
- Steuer 7 %
- exaktes Netto 11,214953271...

Betroffenes Ticket:
- gespeichert 11,21 EUR

Nach Upgrade:
- Ticket-Netto 11,214953271...
- Website/Checkout wieder 12,00 EUR brutto
