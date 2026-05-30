# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .kino_week import DEFAULT_CINETIXX_API_URL, DEFAULT_DISPO_EMAIL


class GlKinoSettingsWizard(models.TransientModel):
    """Eigenständiger Einstellungs-Wizard nur für die Kino-Spielbereitschaft.

    Wichtig: Dieses Modell erbt bewusst NICHT von res.config.settings.
    Dadurch bleibt die normale Odoo-App "Einstellungen" unberührt.
    """

    _name = "gl.kino.settings.wizard"
    _description = "Kino Spielbereitschaft Einstellungen"

    gl_kino_cinetixx_api_url = fields.Char(
        string="Cinetixx-API-URL",
        required=True,
        default=DEFAULT_CINETIXX_API_URL,
    )
    gl_kino_dispo_email = fields.Char(
        string="Dispo-Mailadresse für fehlende DCP/KDM",
        required=True,
        default=DEFAULT_DISPO_EMAIL,
    )
    gl_kino_tuesday_user_id = fields.Many2one(
        "res.users",
        string="Mitarbeiter für Dienstagabend-Erinnerung",
    )
    gl_kino_wednesday_user_ids = fields.Many2many(
        "res.users",
        "gl_kino_settings_wizard_wednesday_user_rel",
        "wizard_id",
        "user_id",
        string="Mitarbeiter für Mittwochmittag-Eskalation",
    )

    @staticmethod
    def _csv_to_ints(raw_value):
        user_ids = []
        for raw in (raw_value or "").split(","):
            raw = raw.strip()
            if raw.isdigit():
                user_ids.append(int(raw))
        return user_ids

    @staticmethod
    def _safe_int(raw_value):
        try:
            return int(raw_value or 0)
        except Exception:
            return 0

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        param = self.env["ir.config_parameter"].sudo()

        if "gl_kino_cinetixx_api_url" in fields_list:
            res["gl_kino_cinetixx_api_url"] = (
                param.get_param("gl_kino_readiness.cinetixx_api_url")
                or DEFAULT_CINETIXX_API_URL
            )

        if "gl_kino_dispo_email" in fields_list:
            res["gl_kino_dispo_email"] = (
                param.get_param("gl_kino_readiness.dispo_email")
                or DEFAULT_DISPO_EMAIL
            )

        if "gl_kino_tuesday_user_id" in fields_list:
            user_id = self._safe_int(param.get_param("gl_kino_readiness.tuesday_user_id"))
            if user_id and self.env["res.users"].browse(user_id).exists():
                res["gl_kino_tuesday_user_id"] = user_id

        if "gl_kino_wednesday_user_ids" in fields_list:
            user_ids = self._csv_to_ints(param.get_param("gl_kino_readiness.wednesday_user_ids"))
            valid_user_ids = self.env["res.users"].browse(user_ids).exists().ids
            res["gl_kino_wednesday_user_ids"] = [(6, 0, valid_user_ids)]

        return res

    def action_save(self):
        self.ensure_one()
        param = self.env["ir.config_parameter"].sudo()
        param.set_param(
            "gl_kino_readiness.cinetixx_api_url",
            (self.gl_kino_cinetixx_api_url or DEFAULT_CINETIXX_API_URL).strip(),
        )
        param.set_param(
            "gl_kino_readiness.dispo_email",
            (self.gl_kino_dispo_email or DEFAULT_DISPO_EMAIL).strip(),
        )
        param.set_param(
            "gl_kino_readiness.tuesday_user_id",
            str(self.gl_kino_tuesday_user_id.id or ""),
        )
        param.set_param(
            "gl_kino_readiness.wednesday_user_ids",
            ",".join(str(user_id) for user_id in self.gl_kino_wednesday_user_ids.ids),
        )
        return {"type": "ir.actions.act_window_close"}
