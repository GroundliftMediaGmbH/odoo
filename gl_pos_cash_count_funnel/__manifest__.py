{
    "name": "Groundlift POS – Kassenzähl-Funnel & Trinkgeldentnahme",
    "summary": "Stückelzählung beim Öffnen und Schließen mit geprüften Cash-Out-Entnahmen",
    "version": "19.0.1.0.2",
    "category": "Point of Sale",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "assets": {
        "point_of_sale._assets_pos": [
            "gl_pos_cash_count_funnel/static/src/js/cash_count_funnel.js",
            "gl_pos_cash_count_funnel/static/src/xml/cash_count_funnel.xml",
            "gl_pos_cash_count_funnel/static/src/scss/cash_count_funnel.scss",
        ],
    },
    "installable": True,
    "application": False,
}
