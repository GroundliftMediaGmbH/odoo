{
    'name': 'Landingpage Text_to_HTML',
    'version': '19.0.1.4.0',
    'summary': 'Groundlift event text mirrored to editable HTML; website renders HTML only',
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
