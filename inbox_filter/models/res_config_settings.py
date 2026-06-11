# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    inbox_filter_openai_api_key = fields.Char(
        string="OpenAI API Token",
        config_parameter="inbox_filter.openai_api_key",
    )
    inbox_filter_openai_model = fields.Char(
        string="OpenAI Modell",
        config_parameter="inbox_filter.openai_model",
        default="gpt-4.1-mini",
        help="Standard: gpt-4.1-mini. Kann bei Bedarf auf ein anderes kompatibles Modell geändert werden.",
    )
    inbox_filter_openai_url = fields.Char(
        string="OpenAI API URL",
        config_parameter="inbox_filter.openai_url",
        default="https://api.openai.com/v1/chat/completions",
    )
    inbox_filter_customer_care_email = fields.Char(
        string="Kundensupport-Adresse",
        config_parameter="inbox_filter.customer_care_email",
        default="customer-care@groundlift.odoo.com",
    )
    inbox_filter_limit = fields.Integer(
        string="Max. Leads pro Sortierlauf",
        config_parameter="inbox_filter.limit",
        default=50,
        help="Schützt vor zu großen API-Läufen. 0 bedeutet: alle Leads in Neu.",
    )
