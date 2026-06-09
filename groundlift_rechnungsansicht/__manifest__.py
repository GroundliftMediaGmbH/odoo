# -*- coding: utf-8 -*-
{
    "name": "Groundlift Rechnungsansicht",
    "summary": "GROUNDLIFT PDF-Rechnungslayout mit USt.-Satz je Position und USt.-Summen je Steuersatz",
    "version": "19.0.3.4.0",
    "category": "Accounting/Accounting",
    "author": "GROUNDLIFT Media GmbH",
    "website": "https://www.groundlift.de",
    "license": "LGPL-3",
    "depends": [
        "account",
        "web",
    ],
    "data": [
        "data/cleanup_legacy_views.xml",
        "data/report_paperformat.xml",
        "views/report_external_layout_invoice.xml",
        "views/report_invoice_templates.xml",
        "data/report_action_setup.xml",
    ],
    "installable": True,
    "application": False,
}
