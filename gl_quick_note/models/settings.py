# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    gl_quick_note_api_key = fields.Char(
        string="OpenAI API-Schlüssel",
        config_parameter="gl_quick_note.api_key",
        groups="base.group_system",
        help="Wird serverseitig in Odoo-Systemparametern gespeichert und niemals an den Browser zurückgegeben, außer in dieser Admin-Einstellung.",
    )
    gl_quick_note_model = fields.Char(
        string="OpenAI-Modell",
        config_parameter="gl_quick_note.model",
        default="gpt-4.1-mini",
        groups="base.group_system",
    )
