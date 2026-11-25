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

## v1.8.0 – Fix für centgenaue POS-Bruttopreise

- Produkt-Netto-Rückrechnung und explizite Brutto-Übernahme verwenden
  `round_globally` und `round_base=False`, unabhängig von der Firmenrundung.
- Migration: nur bereits bruttopreisgesteuerte Produkte neu berechnen. Der
  gespeicherte Bruttopreis bleibt unverändert. Gemeinsame Produkte mit
  widersprüchlichen Steuern verschiedener Firmen werden protokolliert und
  übersprungen, da `list_price` nicht firmenspezifisch ist.
- POS lädt zusätzlich `gross_list_price`. Normale Standardpreise mit einer
  einfachen, nicht im Preis enthaltenen Prozentsteuer (z. B. 7/19 %) werden
  mit einem Odoo-`computation_key` markiert. Er wird über `extra_tax_data`
  gespeichert und in die Rechnung exportiert. Nicht markierte Altbelege,
  abweichende Preislistenpreise, manuelle Sonderpreise und native manuelle
  Steuervorgaben werden nicht auf den Stammpreis zurückgesetzt.
- Der markierte Preis wird nur in der Steuerberechnung als Brutto behandelt;
  `price_unit` bleibt netto. Nach der Odoo-Steuerverteilung wird je markierter
  Position Netto = gerundetes Brutto minus zugeteilte MwSt. gesetzt, ohne die
  zugeteilte MwSt. zu verändern. Frontend und Python nutzen dieselbe Logik.
- Die Steuer-Rundungsmethode der Firma bleibt bestehen; bei globaler Rundung
  können sich MwSt.-Cents zwischen Positionen verschieben, nicht aber deren
  Bruttobeträge. Bestehende Eventticket-Korrekturen bleiben unverändert.
- Grenzen: komplexe Steuergruppen, negative Steuerfaktoren, im Preis bereits
  enthaltene Steuern, Fremdwährungspreise und Sondersteuerdaten verwenden
  weiterhin den Standardweg. Mengenrabatte/Preislisten und manuelle Preise,
  die nicht dem exakten Stammpreis entsprechen, werden nicht fixiert.

### Staging-Check (vor Produktion)

Modul aktualisieren (kein Deinstallieren). POS-Tabs schließen und mit frischen
Assets neu öffnen. Neue Testbestellung mit 36 x 3,60, 8 x 3,00, 3 x 0,70,
19 x 4,50 erstellen. Bei 7 % für Chupa Chups und 19 % für die Getränke sowie
`round_globally`: 241,20 brutto, 38,32 Steuer, 202,88 netto. Zusätzlich einzelne
und getrennte Zeilen, Mengenänderungen, Rabatt, Storno, Bar/Karte (Testmodus),
Rechnung und Kassenabschluss inklusive Buchungssätzen abgleichen. Keine
historischen POS-Bestellungen werden durch die Migration verändert.

Odoo-Tests: `--test-enable --test-tags /gl_gross_sales_price` bei Installation/
Upgrade auf einer separaten Testdatenbank. Python-/JS-Syntax und isolierte
Regressionssimulation lokal geprüft; keine Odoo-SH-Instanz im Build-Umfeld.
