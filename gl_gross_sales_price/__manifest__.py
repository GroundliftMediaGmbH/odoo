{
    "name": "Groundlift Bruttopreis Eingabe",
    "summary": "Bruttopreis eingeben und präzisen Nettopreis auch im Odoo POS beibehalten",
    "version": "19.0.1.1.0",
    "category": "Sales/Point of Sale",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": [
        "product",
        "account",
        "point_of_sale",
    ],
    "data": [
        "views/product_template_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "gl_gross_sales_price/static/src/js/pos_exact_unit_price.js",
        ],
    },
    "installable": True,
    "application": False,
}
