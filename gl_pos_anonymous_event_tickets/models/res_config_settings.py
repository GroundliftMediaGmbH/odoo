# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_gl_anonymous_event_tickets = fields.Boolean(
        string="Anonyme Abendkassen-Tickets",
        related="pos_config_id.gl_anonymous_event_tickets",
        readonly=False,
    )
