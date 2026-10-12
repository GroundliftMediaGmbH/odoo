{
    'name': 'Groundlift Project Showcase',
    'version': '19.0.1.1.0',
    'summary': 'Projektgebundene Kunden-Landingpages mit Vimeo, Dokumenten und Fotogalerie',
    'author': 'Groundlift',
    'website': 'https://www.groundlift.de',
    'category': 'Project',
    'license': 'LGPL-3',
    'depends': ['project', 'website'],
    'data': [
        'security/ir.model.access.csv',
        'security/showcase_rules.xml',
        'views/showcase_views.xml',
        'views/project_views.xml',
        'views/showcase_templates.xml',
    ],
    'installable': True,
    'application': True,
}
