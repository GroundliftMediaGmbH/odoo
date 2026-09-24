{
    'name': 'Landingpage Text_to_HTML',
    'version': '19.0.1.1.0',
    'summary': 'Editable HTML event landing page with safe standard website binding',
    'category': 'Website/Website',
    'author': 'Groundlift',
    'license': 'LGPL-3',
    'depends': ['event', 'website_event'],
    'data': [
        'views/event_event_views.xml',
        'views/website_event_templates.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
