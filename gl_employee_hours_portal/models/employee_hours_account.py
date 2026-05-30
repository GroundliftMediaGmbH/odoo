# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import os
import secrets
from datetime import timedelta
from urllib.parse import quote

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html_escape


PBKDF2_ITERATIONS = 260000


class GlEmployeeHoursAccount(models.Model):
    _name = "gl.employee.hours.account"
    _description = "Mitarbeiter-Stundenportal Konto"
    _order = "employee_id, email"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Mitarbeiter:in",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(related="employee_id.name", store=True, readonly=True)
    email = fields.Char(string="E-Mail", required=True, index=True)
    password_hash = fields.Char(string="Passwort-Hash", readonly=True, copy=False)
    state = fields.Selection(
        [
            ("pending", "Wartet auf E-Mail-Bestätigung"),
            ("active", "Aktiv"),
            ("blocked", "Gesperrt"),
        ],
        default="pending",
        required=True,
        index=True,
    )
    activation_token = fields.Char(string="Aktivierungs-Token", readonly=True, copy=False, index=True)
    activation_expiration = fields.Datetime(string="Aktivierung gültig bis", readonly=True, copy=False)
    reset_token = fields.Char(string="Passwort-Reset-Token", readonly=True, copy=False, index=True)
    reset_expiration = fields.Datetime(string="Passwort-Reset gültig bis", readonly=True, copy=False)
    last_login = fields.Datetime(string="Letzter Login", readonly=True, copy=False)

    _sql_constraints = [
        ("gl_employee_hours_account_email_unique", "unique(email)", "Diese E-Mail ist bereits für das Mitarbeiter-Stundenportal registriert."),
        ("gl_employee_hours_account_employee_unique", "unique(employee_id)", "Für diese Mitarbeiterin / diesen Mitarbeiter existiert bereits ein Stundenportal-Konto."),
    ]

    @api.model
    def _normalize_email(self, email):
        return (email or "").strip().lower()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("email"):
                vals["email"] = self._normalize_email(vals["email"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("email"):
            vals["email"] = self._normalize_email(vals["email"])
        return super().write(vals)

    @api.model
    def _make_password_hash(self, password):
        password = password or ""
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
        return "pbkdf2_sha256${}${}${}".format(
            PBKDF2_ITERATIONS,
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )

    @api.model
    def _verify_password_hash(self, password, password_hash):
        if not password or not password_hash:
            return False
        try:
            algorithm, iterations, salt_b64, digest_b64 = password_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected = base64.b64decode(digest_b64.encode("ascii"))
            calculated = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
            return hmac.compare_digest(expected, calculated)
        except Exception:
            return False

    def set_password(self, password):
        self.ensure_one()
        if not password or len(password) < 8:
            raise UserError(_("Das Passwort muss mindestens 8 Zeichen lang sein."))
        self.write({"password_hash": self._make_password_hash(password)})

    @api.model
    def find_employee_by_email(self, email):
        normalized = self._normalize_email(email)
        if not normalized:
            return self.env["hr.employee"]
        return self.env["hr.employee"].sudo().search([("work_email", "=ilike", normalized)], limit=1)

    @api.model
    def authenticate(self, email, password):
        normalized = self._normalize_email(email)
        account = self.sudo().search([("email", "=", normalized), ("state", "=", "active")], limit=1)
        if not account:
            return self.env[self._name]
        if not self._verify_password_hash(password, account.password_hash):
            return self.env[self._name]
        account.sudo().write({"last_login": fields.Datetime.now()})
        return account

    def _new_token_values(self, prefix, hours_valid):
        token = secrets.token_urlsafe(48)
        return {
            "%s_token" % prefix: token,
            "%s_expiration" % prefix: fields.Datetime.now() + timedelta(hours=hours_valid),
        }

    def create_activation_token(self):
        self.ensure_one()
        vals = self._new_token_values("activation", 72)
        self.sudo().write(vals)
        return vals["activation_token"]

    def create_reset_token(self):
        self.ensure_one()
        vals = self._new_token_values("reset", 4)
        self.sudo().write(vals)
        return vals["reset_token"]

    def activate_from_token(self, token):
        account = self.sudo().search([("activation_token", "=", token)], limit=1)
        if not account:
            raise UserError(_("Der Aktivierungslink ist ungültig."))
        if account.activation_expiration and account.activation_expiration < fields.Datetime.now():
            raise UserError(_("Der Aktivierungslink ist abgelaufen. Bitte registriere dich erneut."))
        account.write({
            "state": "active",
            "activation_token": False,
            "activation_expiration": False,
        })
        return account

    def reset_password_from_token(self, token, password):
        account = self.sudo().search([("reset_token", "=", token), ("state", "=", "active")], limit=1)
        if not account:
            raise UserError(_("Der Passwortlink ist ungültig."))
        if account.reset_expiration and account.reset_expiration < fields.Datetime.now():
            raise UserError(_("Der Passwortlink ist abgelaufen."))
        account.set_password(password)
        account.write({"reset_token": False, "reset_expiration": False})
        return account

    def _email_from(self):
        company = self.env.company
        return company.email_formatted or company.email or self.env.user.email_formatted or self.env.user.email or "notifications@localhost"

    def _send_simple_mail(self, subject, body_html):
        self.ensure_one()
        mail = self.env["mail.mail"].sudo().create({
            "subject": subject,
            "body_html": body_html,
            "email_to": self.email,
            "email_from": self._email_from(),
            "auto_delete": True,
        })
        mail.send()
        return mail

    def send_activation_email(self, base_url):
        self.ensure_one()
        token = self.create_activation_token()
        url = "%s/mitarbeiter/stunden/aktivieren/%s" % (base_url.rstrip("/"), quote(token))
        employee_name = html_escape(self.employee_id.name or "")
        body = """
            <p>Hallo {employee_name},</p>
            <p>für dich wurde ein Zugang zum Mitarbeiter-Stundenportal erstellt.</p>
            <p>Bitte bestätige deine E-Mail-Adresse über diesen Link:</p>
            <p><a href=\"{url}\" style=\"background:#111827;color:#ffffff;padding:10px 16px;text-decoration:none;border-radius:6px;display:inline-block;\">Stundenportal aktivieren</a></p>
            <p>Der Link ist 72 Stunden gültig.</p>
        """.format(employee_name=employee_name, url=html_escape(url))
        return self._send_simple_mail(_("Zugang zum Mitarbeiter-Stundenportal aktivieren"), body)

    def send_reset_email(self, base_url):
        self.ensure_one()
        token = self.create_reset_token()
        url = "%s/mitarbeiter/stunden/passwort-neu/%s" % (base_url.rstrip("/"), quote(token))
        employee_name = html_escape(self.employee_id.name or "")
        body = """
            <p>Hallo {employee_name},</p>
            <p>über diesen Link kannst du dein Passwort für das Mitarbeiter-Stundenportal neu setzen:</p>
            <p><a href=\"{url}\" style=\"background:#111827;color:#ffffff;padding:10px 16px;text-decoration:none;border-radius:6px;display:inline-block;\">Passwort neu setzen</a></p>
            <p>Der Link ist 4 Stunden gültig.</p>
        """.format(employee_name=employee_name, url=html_escape(url))
        return self._send_simple_mail(_("Passwort für Mitarbeiter-Stundenportal zurücksetzen"), body)

    def action_block(self):
        self.write({"state": "blocked"})

    def action_unblock(self):
        self.write({"state": "active"})

    def action_resend_activation_email(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        for account in self:
            if account.state != "active":
                account.send_activation_email(base_url)
