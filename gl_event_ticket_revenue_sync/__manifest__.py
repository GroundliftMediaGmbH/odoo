# -*- coding: utf-8 -*-
{
    "name": "Groundlift Event Ticket Revenue Sync",
    "summary": "Synchronisiert Odoo sale_price_total robust in ein Studio-Feld am Event.",
    "version": "19.0.1.1.0",
    "category": "Events",
    "author": "Groundlift",
    "license": "LGPL-3",
    "depends": [
        "event_sale",
    ],
    "data": [
        "data/ir_cron.xml",
    ],
    "post_init_hook": "_post_init_hook",
    "installable": True,
    "application": False,
}
