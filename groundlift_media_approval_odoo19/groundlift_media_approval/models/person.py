# -*- coding: utf-8 -*-
import hashlib
import hmac

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GlMediaApprovalPerson(models.Model):
    _name = "gl.media.approval.person"
    _description = "Freigabe-Person"
    _order = "name"

    name = fields.Char(required=True)
    email = fields.Char()
    active = fields.Boolean(default=True)
    pin_code = fields.Char(
        string="6-stellige PIN",
        copy=False,
        size=6,
        help="Einfache sechsstellige PIN für den PIN-geschützten Freigabe-Bereich.",
    )
    # Legacy fields from earlier module builds. They remain readable without field-level groups
    # so existing databases do not fail with field access errors during module updates.
    pin_hash = fields.Char(readonly=True, copy=False)
    pin_salt = fields.Char(readonly=True, copy=False)
    pin_set = fields.Boolean(compute="_compute_pin_set", string="PIN gesetzt")
    note = fields.Text()
    vote_ids = fields.One2many("gl.media.approval.vote", "person_id")

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Der Personenname muss eindeutig sein."),
    ]

    @api.depends("pin_code", "pin_hash")
    def _compute_pin_set(self):
        for rec in self:
            rec.pin_set = bool(rec.pin_code or rec.pin_hash)

    @api.model_create_multi
    def create(self, vals_list):
        cleaned = []
        for vals in vals_list:
            vals = dict(vals)
            if "pin_code" in vals:
                vals["pin_code"] = self._normalize_pin(vals.get("pin_code"))
            # Backwards compatibility if an older form still posts pin_plain.
            if vals.get("pin_plain") and not vals.get("pin_code"):
                vals["pin_code"] = self._normalize_pin(vals.pop("pin_plain"))
            else:
                vals.pop("pin_plain", None)
            cleaned.append(vals)
        records = super().create(cleaned)
        records._check_pin_values()
        return records

    def write(self, vals):
        vals = dict(vals)
        if "pin_code" in vals:
            vals["pin_code"] = self._normalize_pin(vals.get("pin_code"))
        # Backwards compatibility if an older form still posts pin_plain.
        if vals.get("pin_plain") and "pin_code" not in vals:
            vals["pin_code"] = self._normalize_pin(vals.pop("pin_plain"))
        else:
            vals.pop("pin_plain", None)
        res = super().write(vals)
        if any(key in vals for key in ("pin_code", "active")):
            self._check_pin_values()
        return res

    @staticmethod
    def _normalize_pin(pin):
        pin = str(pin or "").strip()
        return pin or False

    def _check_pin_values(self):
        for rec in self:
            pin = rec.pin_code
            if not rec.active or not pin:
                continue
            if not pin.isdigit() or len(pin) != 6:
                raise ValidationError(_("Die PIN muss genau aus 6 Ziffern bestehen."))
            duplicate = self.sudo().search([
                ("id", "!=", rec.id),
                ("active", "=", True),
                ("pin_code", "=", pin),
            ], limit=1)
            if duplicate:
                raise ValidationError(_("Diese PIN ist bereits einer anderen aktiven Person zugeordnet."))

    @api.constrains("pin_code", "active")
    def _constrain_pin_code(self):
        self._check_pin_values()

    @staticmethod
    def _hash_pin(pin, salt):
        return hashlib.pbkdf2_hmac("sha256", str(pin).encode("utf-8"), str(salt).encode("utf-8"), 200000).hex()

    def _check_pin(self, pin):
        self.ensure_one()
        pin = str(pin or "").strip()
        if self.pin_code and hmac.compare_digest(str(self.pin_code), pin):
            return True
        # Legacy fallback for databases that still contain old hashed PINs.
        if self.pin_hash and self.pin_salt:
            digest = self._hash_pin(pin, self.pin_salt)
            return hmac.compare_digest(digest, self.pin_hash)
        return False

    @api.model
    def authenticate_pin(self, pin):
        pin = str(pin or "").strip()
        if not pin:
            return self.browse()
        direct = self.sudo().search([("active", "=", True), ("pin_code", "=", pin)], limit=1)
        if direct:
            return direct
        # Legacy fallback for records created with the first hashed-PIN build.
        for person in self.sudo().search([("active", "=", True), ("pin_hash", "!=", False)]):
            if person._check_pin(pin):
                return person
        return self.browse()
