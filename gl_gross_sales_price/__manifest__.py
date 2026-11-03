{
    "name": "Groundlift Bruttopreis Eingabe",
    "summary": "Stabiler Bruttopreis, exakter Nettopreis und Event-Ticket-Rundungsschutz für Odoo 19",
    "version": "19.0.1.6.0",
    "category": "Sales/Point of Sale",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": [
        "product",
        "account",
        "point_of_sale",
        "event_product",
        "event_sale",
    ],
    "data": [
        "views/product_template_views.xml",
        "views/product_template_actions.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "gl_gross_sales_price/static/src/js/pos_exact_unit_price.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
