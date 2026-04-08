{
    'name': 'Custom Event Hero Image',
    'version': '1.0',
    'category': 'Website/Events',
    'summary': 'Ersetzt das Standard-Event-Cover durch ein Studio-Feld (x_studio_website_header)',
    'description': 'Liest das manuell angelegte Bild aus und setzt es als Hero-Image auf der Event-Seite.',
    'author': 'Dein Name/Unternehmen',
    'depends': ['website_event'],
    'data': [
        'views/templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}