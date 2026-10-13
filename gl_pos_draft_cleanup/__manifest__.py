{
    "name": "Groundlift POS - Drafts löschen",
    "summary": "Sichere Bereinigung verwaister POS-Entwürfe beim Kassenabschluss",
    "version": "19.0.1.0.0",
    "category": "Point of Sale",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": ["point_of_sale"],
    "assets": {
        "point_of_sale._assets_pos": [
            "gl_pos_draft_cleanup/static/src/closing_popup.js",
            "gl_pos_draft_cleanup/static/src/closing_popup.xml",
        ],
    },
    "installable": True,
    "application": False,
}
