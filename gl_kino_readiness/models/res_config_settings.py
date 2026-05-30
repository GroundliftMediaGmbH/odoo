# -*- coding: utf-8 -*-
from odoo import fields, models

from .kino_week import DEFAULT_CINETIXX_API_URL, DEFAULT_DISPO_EMAIL


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    gl_kino_cinetixx_api_url = fields.Char(
        string="Cinetixx-API-URL",
        default=DEFAULT_CINETIXX_API_URL,
        config_parameter="gl_kino_readiness.cinetixx_api_url",
    )
    gl_kino_dispo_email = fields.Char(
        string="Dispo-Mailadresse für fehlende DCP/KDM",
        default=DEFAULT_DISPO_EMAIL,
        config_parameter="gl_kino_readiness.dispo_email",
    )
    gl_kino_tuesday_user_id = fields.Many2one(
        "res.users",
        string="Mitarbeiter für Dienstagabend-Erinnerung",
        config_parameter="gl_kino_readiness.tuesday_user_id",
    )
    gl_kino_wednesday_user_ids = fields.Many2many(
        "res.users",
        "gl_kino_settings_wednesday_user_rel",
        "settings_id",
        "user_id",
        string="Mitarbeiter für Mittwochmittag-Eskalation",
    )

    def get_values(self):
        res = super().get_values()
        param = self.env["ir.config_parameter"].sudo()
        raw_user_ids = param.get_param("gl_kino_readiness.wednesday_user_ids") or ""
        user_ids = []
        for raw in raw_user_ids.split(","):
            raw = raw.strip()
            if raw.isdigit():
                user_ids.append(int(raw))
        res.update(gl_kino_wednesday_user_ids=[(6, 0, self.env["res.users"].browse(user_ids).exists().ids)])
        return res

    def set_values(self):
        super().set_values()
        param = self.env["ir.config_parameter"].sudo()
        param.set_param(
            "gl_kino_readiness.wednesday_user_ids",
            ",".join(str(user_id) for user_id in self.gl_kino_wednesday_user_ids.ids),
        )
