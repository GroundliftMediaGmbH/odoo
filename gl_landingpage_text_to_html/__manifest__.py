{
    'name': 'Landingpage Text_to_HTML',
    'version': '19.0.2.1.0',
    'summary': 'Groundlift event text mirrored to editable HTML and public Odoo event description',
    'category': 'Website/Website',
    'author': 'Groundlift',
    'license': 'LGPL-3',
    'depends': ['event', 'website_event'],
    'data': [
        'views/event_event_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
