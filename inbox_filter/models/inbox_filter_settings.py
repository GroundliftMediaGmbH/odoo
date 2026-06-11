# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class InboxFilterSettings(models.Model):
    _name = "inbox.filter.settings"
    _description = "Inbox Filter Einstellungen"
    _rec_name = "name"

    name = fields.Char(default="Inbox Filter Einstellungen", required=True)
    openai_api_key = fields.Char(
        string="OpenAI API Token",
        copy=False,
        help="Der Token wird direkt in diesem Einstellungsdatensatz gespeichert."
    )
    openai_api_key_status = fields.Char(
        string="Token-Status",
        compute="_compute_openai_api_key_status",
        readonly=True,
    )
    openai_model = fields.Char(
        string="OpenAI Modell",
        default="gpt-4.1-mini",
        required=True,
        help="Standard: gpt-4.1-mini. Kann bei Bedarf geändert werden.",
    )
    openai_url = fields.Char(
        string="OpenAI API URL",
        default="https://api.openai.com/v1/chat/completions",
        required=True,
    )
    customer_care_email = fields.Char(
        string="Kundensupport-Adresse",
        default="customer-care@groundlift.odoo.com",
        required=True,
    )
    limit = fields.Integer(
        string="Max. Leads pro Sortierlauf",
        default=50,
        help="Schützt vor zu großen API-Läufen. 0 bedeutet: alle Leads in Neu.",
    )
    auto_sort_enabled = fields.Boolean(
        string="Automatisch sortieren",
        default=True,
        help="Wenn aktiv, wird jeder neu in CRM Neu eingehende Datensatz sofort automatisch analysiert und einsortiert.",
    )

    @api.depends("openai_api_key")
    def _compute_openai_api_key_status(self):
        for record in self:
            token = (record.openai_api_key or "").strip()
            record.openai_api_key_status = _("Gespeichert: %s") % self._mask_token(token) if token else _("Nicht gespeichert")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_to_ir_config_parameter()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._sync_to_ir_config_parameter()
        return res

    @api.model
    def get_singleton(self):
        record = self.sudo().search([], order="id asc", limit=1)
        if not record:
            params = self.env["ir.config_parameter"].sudo()
            record = self.sudo().create({
                "name": "Inbox Filter Einstellungen",
                "openai_api_key": (params.get_param("inbox_filter.openai_api_key", "") or "").strip(),
                "openai_model": (params.get_param("inbox_filter.openai_model", "gpt-4.1-mini") or "gpt-4.1-mini").strip(),
                "openai_url": (params.get_param("inbox_filter.openai_url", "https://api.openai.com/v1/chat/completions") or "https://api.openai.com/v1/chat/completions").strip(),
                "customer_care_email": (params.get_param("inbox_filter.customer_care_email", "customer-care@groundlift.odoo.com") or "customer-care@groundlift.odoo.com").strip(),
                "limit": int(params.get_param("inbox_filter.limit", "50") or 50),
                "auto_sort_enabled": (params.get_param("inbox_filter.auto_sort_enabled", "1") or "1") not in ("0", "False", "false"),
            })
        return record

    def action_test_openai_token_saved(self):
        self.ensure_one()
        token = (self.openai_api_key or "").strip()
        if not token:
            raise UserError(_("Es ist noch kein OpenAI API Token gespeichert."))
        self._sync_to_ir_config_parameter()
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
        self.ensure_one()
        self.write({"openai_api_key": False})
        self.env["ir.config_parameter"].sudo().set_param("inbox_filter.openai_api_key", "")
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

    def _sync_to_ir_config_parameter(self):
        """Spiegelung für bestehende Service-/Upgrade-Pfade.

        Die primäre Speicherung erfolgt ab v104 im echten Modell
        `inbox.filter.settings`. `ir.config_parameter` bleibt nur Fallback.
        """
        params = self.env["ir.config_parameter"].sudo()
        for record in self.sudo():
            if record.openai_api_key:
                params.set_param("inbox_filter.openai_api_key", (record.openai_api_key or "").strip())
            params.set_param("inbox_filter.openai_model", (record.openai_model or "gpt-4.1-mini").strip())
            params.set_param("inbox_filter.openai_url", (record.openai_url or "https://api.openai.com/v1/chat/completions").strip())
            params.set_param("inbox_filter.customer_care_email", (record.customer_care_email or "customer-care@groundlift.odoo.com").strip())
            params.set_param("inbox_filter.limit", str(record.limit or 0))
            params.set_param("inbox_filter.auto_sort_enabled", "1" if record.auto_sort_enabled else "0")

    @api.model
    def _mask_token(self, token):
        token = token or ""
        if len(token) <= 12:
            return "••••"
        return "%s…%s" % (token[:7], token[-4:])
