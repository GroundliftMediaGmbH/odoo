{
    'name': 'Landingpage Text_to_HTML',
    'version': '19.0.1.8.0',
    'summary': 'Groundlift event text mirrored to editable HTML and native Odoo event description',
    'category': 'Website/Website',
    'author': 'Groundlift',
    'license': 'LGPL-3',
    'depends': ['event', 'website_event'],
    # Deliberately NO website/QWeb inheritance here. The public event page uses
    # Odoo's native event.description, which is kept identical to our HTML field.
    'data': [
        'views/event_event_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
