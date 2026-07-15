# Groundlift Event Ticket Labels – Odoo 19 SH

Dieses Modul ändert den Ticket-Auswahldialog auf öffentlichen Veranstaltungsseiten:

- Sobald mindestens ein Ticket mit einem Preis **größer als 0,00 €** vorhanden ist, werden öffentlich ausschließlich die kostenpflichtigen Ticketarten angeboten.
- Kostenlose Ticketarten, beispielsweise interne **Gästelistentickets**, bleiben dann im öffentlichen Dialog verborgen.
- Gibt es für eine Veranstaltung dagegen **ausschließlich kostenlose Tickets**, werden diese ganz normal angezeigt und können gebucht werden.
- Die Preisanzeige im Kopf des Dialogs berücksichtigt dieselbe Regel.
- Bei generischen oder doppelten Ticketnamen wie **Registrierung** wird der Name des verknüpften Produkts angezeigt, z. B. **Stehplatz** oder **Sitzplatz**.
- Individuell gepflegte Ticketnamen bleiben erhalten.
- Der rote Absende-Button heißt **Tickets kaufen**.
- Funktioniert bei einzelnen und mehreren Tickettypen sowie bei reinen Kostenlos-Veranstaltungen.

## Update auf Odoo.sh

1. Den bestehenden Ordner `groundlift_event_ticket_labels` im GitHub-Repository vollständig durch diesen Ordner ersetzen.
2. Commit und Push ausführen.
3. In Odoo unter **Apps** das Modul **Groundlift Event Ticket Labels** öffnen und **Aktualisieren** wählen.
4. Die Veranstaltungsseite anschließend mit `Strg + F5` neu laden.

## Voraussetzung

Das Odoo-Modul `website_event_sale` muss installiert sein.
