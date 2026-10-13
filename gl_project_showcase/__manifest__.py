{
    'name': 'Groundlift Project Showcase',
    'version': '19.0.1.6.0',
    'summary': 'Projektgebundene Kunden-Landingpages mit Vimeo, Dokumenten und Fotogalerie',
    'author': 'Groundlift',
    'website': 'https://www.groundlift.de',
    'category': 'Project',
    'license': 'LGPL-3',
    'depends': ['project', 'website'],
    'external_dependencies': {'python': ['pypdfium2']},
    'data': [
        'security/ir.model.access.csv',
        'security/showcase_rules.xml',
        'views/showcase_views.xml',
        'views/settings_views.xml',
        'views/project_views.xml',
        'views/showcase_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'gl_project_showcase/static/src/css/showcase_backend.css',
        ],
    },
    'installable': True,
    'application': True,
}
