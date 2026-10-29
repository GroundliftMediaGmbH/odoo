{
    "name": "Groundlift Bruttopreis Eingabe",
    "summary": "Bruttopreis eingeben und Rundungsfehler im Odoo 19 POS vermeiden",
    "version": "19.0.1.3.0",
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
        "views/product_template_actions.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "gl_gross_sales_price/static/src/js/pos_exact_unit_price.js",
            "gl_gross_sales_price/static/src/js/pos_gross_tax_rounding.js",
        ],
    },
    "installable": True,
    "application": False,
}
