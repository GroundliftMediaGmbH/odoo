# -*- coding: utf-8 -*-
{
    "name": "Groundlift Rechnungsansicht",
    "summary": "GROUNDLIFT PDF-Rechnungslayout im Stil der Farbe-Blau-Referenz",
    "version": "19.0.2.0.0",
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
        "views/report_external_layout_invoice.xml",
        "views/report_invoice_document.xml",
        "views/report_invoice_language.xml",
        "data/report_action_setup.xml",
    ],
    "installable": True,
    "application": False,
}
