{
    'name': 'Landingpage Text_to_HTML',
    'version': '19.0.1.6.0',
    'summary': 'Groundlift event text mirrored to editable HTML; HTML is the canonical public event description',
    'category': 'Website/Website',
    'author': 'Groundlift',
    'license': 'LGPL-3',
    'depends': ['event', 'website_event'],
    # IMPORTANT: no website template inheritance here.  The standard Odoo
    # event page keeps rendering event.description, and this module makes that
    # field an exact mirror of gl_landingpage_html.  This avoids brittle XPath
    # dependencies on Odoo/Website Builder/third-party templates.
    'data': [
        'views/event_event_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
}
