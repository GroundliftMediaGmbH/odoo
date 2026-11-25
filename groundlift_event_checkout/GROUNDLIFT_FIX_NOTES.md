# Groundlift Event Checkout – Fix 19.0.1.1.10 (Odoo 19 SH)

## Fehlerbild
Acht bestätigte Websiteaufträge hatten insgesamt 16 Anmeldungen mit `sale_status=sold`, `state=draft` und ohne E-Mail-Planung. Die betroffenen Anmeldungen wurden erst beim Zahlungsabschluss erzeugt. Der Kundendaten-RPC-Marker war nicht vorhanden. Der Wert `meta_source_url=/shop/confirmation` stammt möglicherweise vom Meta Pixel und belegt **nicht**, dass der One-Page-Checkout besucht wurde.

## Änderungen zu 19.0.1.1.8
- Neue `controllers/payment.py`: in der Standardroute `/shop/payment/transaction/<order_id>` werden Registrierungen für Website-Ticketbestellungen vor Zahlungsabwicklung angelegt, falls sie fehlen. Der Schutz hängt **nicht** davon ab, ob der User vorher `/groundlift/checkout` besucht hat.
- `controllers/main.py`: eine Session-Kennung wird allein zur Diagnose beim Anzeigen des One-Page-Checkouts gespeichert. Sie ist kein Eintrittskriterium für die Absicherung.
- `controllers/__init__.py`: lädt `payment.py`.
- Neue Modulversion 19.0.1.1.10.
- Sonst keine Änderungen an JS, Preis-/Gutscheinberechnung, Kundenformular, Newsletter, Meta Pixel, Versand oder sonstigen Modulen.

Die vorhandene RPC-Kundendatenverarbeitung bleibt unverändert. Der Backend-/POS-Verkauf ist nicht betroffen. Es erfolgt kein automatisches Nachbessern historischer Tickets und keine Mail vor erfolgreicher Zahlung. Bei Misserfolg der Ticketvorbereitung wird die Erstellung des Zahlungsvorgangs mit einer Fehlermeldung abgebrochen.

## Wichtige Staging-Tests
1. Normale Website-Ticketzahlung, Gast und angemeldeter Kunde: Registrierungen vorhanden bevor Zahlungsanbieter startet, nach `done` alle `open` und Mailplanung vorhanden.
2. Umleitung zum Odoo-Standard-Checkout und Zahlungsmethode mit gespeichertem Token: Absicherung greift auch ohne Session-Marker.
3. Abgebrochene Zahlung, Zahlungswiederholung, Gutscheine sowie gemischte Warenkörbe prüfen.
4. Mit blockiertem `checkout.js` und vorhandenen gültigen Kundendaten prüfen, dass Zahlung trotzdem keinen `sale/sold/draft`-Endzustand erzeugt.
5. Odoo.sh-Log nach `Groundlift pre-payment registration fallback` durchsuchen.
6. Keine automatische Reparatur der 16 historischen Anmeldungen.

Getestet: Python-AST, XML-Parsing, ZIP-Integrität und isolierte Mock-Tests. Kein Live-Integrationstest gegen Groundlift Odoo.sh möglich.
