# Groundlift Event Ticket Labels – Odoo 19 SH

Dieses Modul ändert den Ticket-Auswahldialog auf öffentlichen Veranstaltungsseiten:

- Es werden ausschließlich Ticketarten mit einem Preis **größer als 0,00 €** angeboten.
- Kostenlose Ticketarten, beispielsweise interne **Gästelistentickets**, bleiben in Odoo erhalten, werden auf der öffentlichen Veranstaltungsseite jedoch nicht angezeigt.
- Auch die Preisspanne im Kopf des Dialogs berücksichtigt nur kostenpflichtige Tickets.
- Bei generischen oder doppelten Ticketnamen wie **Registrierung** wird der Name des verknüpften Produkts angezeigt, z. B. **Stehplatz** oder **Sitzplatz**.
- Individuell gepflegte Ticketnamen bleiben erhalten.
- Der rote Absende-Button heißt **Tickets kaufen**.
- Funktioniert sowohl bei einem einzelnen kostenpflichtigen Tickettyp als auch bei mehreren Tickettypen.

## Update auf Odoo.sh

1. Den bestehenden Ordner `groundlift_event_ticket_labels` im GitHub-Repository vollständig durch diesen Ordner ersetzen.
2. Commit und Push ausführen.
3. In Odoo unter **Apps** das Modul **Groundlift Event Ticket Labels** öffnen und **Aktualisieren** wählen.
4. Die Veranstaltungsseite anschließend mit `Strg + F5` neu laden.

## Voraussetzung

Das Odoo-Modul `website_event_sale` muss installiert sein.
