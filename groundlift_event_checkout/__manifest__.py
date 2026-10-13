{
    "name": "Groundlift Event One-Page Checkout",
    "version": "19.0.1.1.8",
    "summary": "Direct ticket selection and one-page customer/payment checkout for Groundlift events",
    "category": "Website/eCommerce",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": [
        "website_event_sale",
        "website_sale",
        "payment",
        "meta_pixel",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/event_templates.xml",
        "views/checkout_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "groundlift_event_checkout/static/src/js/checkout.js",
            "groundlift_event_checkout/static/src/scss/checkout.scss",
        ],
    },
    "installable": True,
    "application": False,
}
