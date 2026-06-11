# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    inbox_filter_openai_api_key = fields.Char(
        string="OpenAI API Token",
        help=(
            "Neuen Token hier einfügen. Ein bereits gespeicherter Token wird beim Öffnen "
            "wieder geladen und beim Speichern nicht versehentlich geleert."
        ),
    )
    inbox_filter_openai_api_key_status = fields.Char(
        string="Token-Status",
        compute="_compute_inbox_filter_openai_api_key_status",
        readonly=True,
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

    @api.depends_context("uid")
    def _compute_inbox_filter_openai_api_key_status(self):
        token = self.env["ir.config_parameter"].sudo().get_param("inbox_filter.openai_api_key", "") or ""
        token = token.strip()
        if token:
            masked = self._mask_token(token)
            status = _("Gespeichert: %s") % masked
        else:
            status = _("Nicht gespeichert")
        for record in self:
            record.inbox_filter_openai_api_key_status = status

    @api.model
    def get_values(self):
        res = super().get_values()
        params = self.env["ir.config_parameter"].sudo()
        token = (params.get_param("inbox_filter.openai_api_key", "") or "").strip()
        # Explizit laden, damit das Feld beim erneuten Öffnen nicht leer erscheint.
        res.update({
            "inbox_filter_openai_api_key": token,
        })
        return res

    def set_values(self):
        super().set_values()
        params = self.env["ir.config_parameter"].sudo()
        for record in self:
            token = (record.inbox_filter_openai_api_key or "").strip()
            # Wichtig: Ein leeres Passwortfeld soll einen bestehenden Token NICHT versehentlich löschen.
            # Löschen geht bewusst über den Button "Token entfernen".
            if token:
                params.set_param("inbox_filter.openai_api_key", token)

    def action_test_openai_token_saved(self):
        token = (self.env["ir.config_parameter"].sudo().get_param("inbox_filter.openai_api_key", "") or "").strip()
        if not token:
            raise UserError(_("Es ist noch kein OpenAI API Token gespeichert."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Inbox Filter"),
                "message": _("OpenAI API Token ist gespeichert: %s") % self._mask_token(token),
                "type": "success",
                "sticky": False,
            },
        }

    def action_clear_openai_token(self):
        self.env["ir.config_parameter"].sudo().set_param("inbox_filter.openai_api_key", "")
        for record in self:
            record.inbox_filter_openai_api_key = False
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Inbox Filter"),
                "message": _("OpenAI API Token wurde entfernt."),
                "type": "warning",
                "sticky": False,
            },
        }

    @api.model
    def _mask_token(self, token):
        token = token or ""
        if len(token) <= 12:
            return "••••"
        return "%s…%s" % (token[:7], token[-4:])
