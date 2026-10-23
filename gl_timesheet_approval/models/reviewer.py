# -*- coding: utf-8 -*-
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GlTimesheetReviewer(models.Model):
    _name = "gl.timesheet.reviewer"
    _description = "Stundenzettel-Prüfer"
    _order = "reviewer_level, name"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    reviewer_level = fields.Selection(
        [("1", "1. Prüfer"), ("2", "2. Prüfer")],
        string="Prüfer-Kategorie",
        required=True,
        default="1",
    )
    auth_mode = fields.Selection(
        [("odoo", "Bestehenden Odoo-Benutzer verwenden"), ("custom", "Freie Zugangsdaten")],
        string="Anmeldung",
        required=True,
        default="odoo",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Odoo-Benutzer",
        ondelete="cascade",
    )
    custom_login = fields.Char(string="Freier Benutzername", copy=False)
    new_password = fields.Char(
        string="Neues Passwort",
        copy=False,
        help="Das Passwort wird ausschließlich als sicherer Hash gespeichert und ist nach dem Speichern nicht mehr sichtbar.",
    )
    password_hash = fields.Char(copy=False, groups="base.group_system")
    password_is_set = fields.Boolean(compute="_compute_password_is_set", compute_sudo=True)
    email = fields.Char(
        string="E-Mail für freie Zugangsdaten",
        help="Bei Odoo-Benutzern wird automatisch die E-Mail des Benutzers verwendet.",
    )
    effective_email = fields.Char(compute="_compute_effective_email", string="Benachrichtigungs-E-Mail")
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    failed_login_count = fields.Integer(default=0, copy=False)
    lock_until = fields.Datetime(copy=False)
    last_login_at = fields.Datetime(copy=False)

    _sql_constraints = [
        (
            "custom_login_company_unique",
            "unique(custom_login, company_id)",
            "Dieser freie Benutzername ist in der Firma bereits vergeben.",
        ),
        (
            "user_company_unique",
            "unique(user_id, company_id)",
            "Dieser Odoo-Benutzer ist in der Firma bereits als Prüfer hinterlegt.",
        ),
    ]

    @api.depends("password_hash")
    def _compute_password_is_set(self):
        for reviewer in self:
            reviewer.password_is_set = bool(reviewer.sudo().password_hash)

    @api.depends("auth_mode", "email", "user_id.email", "user_id.partner_id.email")
    def _compute_effective_email(self):
        for reviewer in self:
            reviewer.effective_email = (
                reviewer.user_id.email or reviewer.user_id.partner_id.email
                if reviewer.auth_mode == "odoo" and reviewer.user_id
                else reviewer.email
            )

    @api.constrains("auth_mode", "user_id", "custom_login", "email", "password_hash")
    def _check_auth_configuration(self):
        for reviewer in self:
            if reviewer.auth_mode == "odoo" and not reviewer.user_id:
                raise ValidationError(_("Für diese Anmeldeart muss ein Odoo-Benutzer gewählt werden."))
            if reviewer.auth_mode == "custom":
                if not reviewer.custom_login:
                    raise ValidationError(_("Für freie Zugangsdaten muss ein Benutzername vergeben werden."))
                if not reviewer.password_hash:
                    raise ValidationError(_("Für freie Zugangsdaten muss ein Passwort vergeben werden."))
                if not reviewer.email:
                    raise ValidationError(_("Für freie Zugangsdaten muss eine E-Mail-Adresse hinterlegt werden."))

    @api.constrains("custom_login", "company_id")
    def _check_custom_login_case_insensitive(self):
        for reviewer in self.filtered(lambda r: r.custom_login):
            normalized_login = reviewer.custom_login.strip().casefold()
            candidates = self.search(
                [
                    ("id", "!=", reviewer.id),
                    ("company_id", "=", reviewer.company_id.id),
                    ("custom_login", "!=", False),
                ]
            )
            if any((candidate.custom_login or "").strip().casefold() == normalized_login for candidate in candidates):
                raise ValidationError(_("Dieser freie Benutzername ist bereits vergeben."))

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            raw_password = vals.pop("new_password", False)
            if vals.get("custom_login"):
                vals["custom_login"] = vals["custom_login"].strip()
            if raw_password:
                vals["password_hash"] = generate_password_hash(raw_password)
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        vals = dict(vals)
        raw_password = vals.pop("new_password", False)
        if vals.get("custom_login"):
            vals["custom_login"] = vals["custom_login"].strip()
        if raw_password:
            vals["password_hash"] = generate_password_hash(raw_password)
            vals.update({"failed_login_count": 0, "lock_until": False})
        return super().write(vals)

    def _check_custom_password(self, raw_password):
        self.ensure_one()
        if self.auth_mode != "custom" or not self.active or not self.password_hash:
            return False
        now = fields.Datetime.now()
        if self.lock_until and self.lock_until > now:
            return False

        valid = check_password_hash(self.password_hash, raw_password or "")
        if valid:
            self.sudo().write(
                {
                    "failed_login_count": 0,
                    "lock_until": False,
                    "last_login_at": now,
                }
            )
            return True

        failed_count = self.failed_login_count + 1
        values = {"failed_login_count": failed_count}
        if failed_count >= 5:
            values["lock_until"] = now + timedelta(minutes=15)
            values["failed_login_count"] = 0
        self.sudo().write(values)
        return False

    def action_open_portal(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": "/stundenzettel/pruefung",
            "target": "new",
        }
