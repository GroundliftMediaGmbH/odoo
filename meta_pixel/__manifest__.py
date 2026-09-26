{
    "name": "Meta Pixel",
    "version": "19.0.1.0.5",
    "summary": "Event-specific Meta Pixel and Conversions API tracking with reporting",
    "category": "Marketing/Events",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": [
        "event_sale",
        "website_event_sale",
        "website_sale",
        "payment",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data_meta_pixel_cron.xml",
        "views/meta_pixel_config_views.xml",
        "views/meta_pixel_log_views.xml",
        "views/event_event_views.xml",
        "views/res_config_settings_views.xml",
        "views/website_templates.xml",
        "views/menu_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "meta_pixel/static/src/js/meta_pixel_frontend.js",
        ],
    },
    "application": True,
    "installable": True,
}
