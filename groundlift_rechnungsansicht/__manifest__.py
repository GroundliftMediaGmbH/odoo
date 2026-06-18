# -*- coding: utf-8 -*-
{
    "name": "Groundlift Rechnungsansicht",
    "summary": "GROUNDLIFT PDF-Rechnungslayout mit Freitexten und USt.-Aufschlüsselung",
    "version": "19.0.3.6.1",
    "category": "Accounting/Accounting",
    "author": "GROUNDLIFT Media GmbH",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": [
        "account",
        "sale",
        "web",
    ],
    "data": [
        "data/cleanup_legacy_views.xml",
        "data/report_paperformat.xml",
        "views/account_move_views.xml",
        "views/report_external_layout_invoice.xml",
        "views/report_invoice_templates.xml",
        "data/report_action_setup.xml",
    ],
    "installable": True,
    "application": False,
}
