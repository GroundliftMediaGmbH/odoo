{
    "name": "Grafiken",
    "summary": "Erstellt Kino-Veranstaltungsplakate direkt aus Odoo-Events",
    "version": "19.0.1.3.6",
    "category": "Marketing",
    "author": "GROUNDLIFT",
    "website": "https://groundlift.de",
    "license": "LGPL-3",
    "depends": ["base", "web", "event", "website_event"],
    "data": [
        "security/ir.model.access.csv",
        "security/graphics_security.xml",
        "data/graphics_template_data.xml",
        "views/graphics_poster_views.xml",
        "views/graphics_template_views.xml",
        "views/event_event_views.xml",
        "views/graphics_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "groundlift_graphics/static/src/js/graphics_editor_loader.js",
        ],
    },
    "images": ["static/description/icon.png"],
    "application": True,
    "installable": True,
}
