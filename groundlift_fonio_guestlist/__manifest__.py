# -*- coding: utf-8 -*-
{
    'name': 'Groundlift Fonio Gästeliste',
    'version': '19.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Überträgt Fonio-Kartenreservierungen automatisch aus Kundendiensttickets auf die Event-Gästeliste',
    'description': """
Groundlift Fonio Gästeliste
===========================

Dieses Modul verarbeitet Fonio-Reservierungsanfragen, die per E-Mail als
Kundendienstticket im Team "Kartenreservierung" eingehen.

Aus den Fonio-Daten in der Ticketbeschreibung werden automatisch Gästelistenplätze
im vorhandenen Groundlift-Gästelistenmodul erzeugt. Danach wird das Ticket in die
Phase "Gelöst" verschoben.
    """,
    'author': 'Groundlift Media GmbH',
    'website': 'https://www.groundlift.de',
    'license': 'LGPL-3',
    'depends': [
        'helpdesk',
        'gl_event_guestlist',
    ],
    'data': [
        'data/ir_config_parameter.xml',
        'data/ir_cron.xml',
        'views/helpdesk_ticket_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
