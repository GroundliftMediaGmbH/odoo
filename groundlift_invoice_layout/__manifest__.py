# -*- coding: utf-8 -*-
{
    "name": "GROUNDLIFT Invoice Layout",
    "summary": "GROUNDLIFT PDF-Rechnungslayout auf Basis des Odoo Wave External Layouts",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "author": "GROUNDLIFT Media GmbH",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": [
        "account",
        "web",
    ],
    "data": [
        "data/report_paperformat.xml",
        "views/report_external_layout_wave.xml",
        "data/report_action_setup.xml",
    ],
    "installable": True,
    "application": False,
}
