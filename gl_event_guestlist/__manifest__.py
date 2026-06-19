# -*- coding: utf-8 -*-
{
    'name': 'Groundlift Event Gästeliste',
    'version': '19.0.1.2.0',
    'category': 'Marketing/Events',
    'summary': 'Gästeliste mit QR-Check-in direkt an Veranstaltungen',
    'description': """
Groundlift Event Gästeliste
===========================

Erweitert die Veranstaltungsapp um einen Tab "Gästeliste".
Gäste können je Veranstaltung mit Anzahl, Bearbeiter, Preisoption,
Bestellweg, Kontaktdaten und Bemerkung gepflegt werden.

Die Gästelisten-Anzahl wird gegen die verfügbare Ticketkapazität geprüft.
Wenn verkaufte/registrierte Plätze plus verbindliche Gästelistenplätze die globale Registrierungsbeschränkung erreichen, wird der Veranstaltungsname automatisch mit "(Ausverkauft)" ergänzt und die Registrierung auf der Website geschlossen.
Wartelisten-Einträge werden als eigene Kategorie geführt und nicht auf die Kapazität angerechnet.
Im Tickets-Tab wird zusätzlich eine technische Summenzeile "Gästeliste" ohne Produkt erzeugt,
deren Registrierungszahl der Summe der verbindlichen Gästelistenplätze ohne Warteliste entspricht.
Zusätzlich erzeugt jede Veranstaltung einen QR-Link auf eine öffentliche,
token-geschützte Check-in-Seite zum Abhaken der Gäste.
    """,
    'author': 'Groundlift Media GmbH',
    'website': 'https://www.groundlift.de',
    'license': 'LGPL-3',
    'depends': [
        'event_sale',
        'website',
        'hr',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/guestlist_summary_ticket_data.xml',
        'views/event_guestlist_views.xml',
        'views/guestlist_templates.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
