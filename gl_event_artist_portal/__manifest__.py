# -*- coding: utf-8 -*-
{
    'name': 'Groundlift Künstler- & Agenturportal',
    'version': '19.0.1.0.0',
    'category': 'Marketing/Events',
    'summary': 'Token-geschütztes Künstlerportal für Gästeliste, Abendkasse und Ticketstände',
    'description': """
Groundlift Künstler- & Agenturportal
====================================

Erweitert Veranstaltungen in der Phase „Angekündigt“ um eine token-geschützte
öffentliche Seite für Künstler und Agenturen. Dort können kostenlose
Gästelistenplätze sowie an der Abendkasse zu zahlende Tickets eingetragen und
aktuelle Ticketstände eingesehen werden.

Die Einträge werden direkt in der bestehenden App „Groundlift Event Gästeliste“
als gl.event.guestlist.line gespeichert und verwenden deren Kapazitätsprüfung.
    """,
    'author': 'Groundlift Media GmbH',
    'website': 'https://www.groundlift.de',
    'license': 'LGPL-3',
    'depends': [
        'gl_event_guestlist',
        'website',
    ],
    'data': [
        'data/artist_portal_data.xml',
        'views/event_artist_portal_views.xml',
        'views/artist_portal_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'gl_event_artist_portal/static/src/css/artist_portal.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
