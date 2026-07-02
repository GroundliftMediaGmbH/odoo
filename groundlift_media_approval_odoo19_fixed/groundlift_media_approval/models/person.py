# -*- coding: utf-8 -*-
import hashlib
import hmac
import secrets

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GlMediaApprovalPerson(models.Model):
    _name = "gl.media.approval.person"
    _description = "Freigabe-Person"
    _order = "name"

    name = fields.Char(required=True)
    email = fields.Char()
    active = fields.Boolean(default=True)
    pin_hash = fields.Char(readonly=True, copy=False, groups="groundlift_media_approval.group_media_approval_manager")
    pin_salt = fields.Char(readonly=True, copy=False, groups="groundlift_media_approval.group_media_approval_manager")
    pin_set = fields.Boolean(compute="_compute_pin_set", string="PIN gesetzt")
    pin_plain = fields.Char(
        string="PIN setzen/ändern",
        compute="_compute_pin_plain",
        inverse="_inverse_pin_plain",
        store=False,
        password=True,
        help="PIN hier eingeben und speichern. Aus Sicherheitsgründen wird nur ein Hash gespeichert.",
    )
    note = fields.Text()
    vote_ids = fields.One2many("gl.media.approval.vote", "person_id")

    _sql_constraints = [
        ("name_uniq", "unique(name)", "Der Personenname muss eindeutig sein."),
    ]

    @api.depends("pin_hash")
    def _compute_pin_set(self):
        for rec in self:
            rec.pin_set = bool(rec.pin_hash)

    def _compute_pin_plain(self):
        for rec in self:
            rec.pin_plain = ""

    def _inverse_pin_plain(self):
        for rec in self:
            if rec.pin_plain:
                rec._set_pin(rec.pin_plain)

    @api.model_create_multi
    def create(self, vals_list):
        pins = []
        cleaned = []
        for vals in vals_list:
            vals = dict(vals)
            pins.append(vals.pop("pin_plain", False))
            cleaned.append(vals)
        records = super().create(cleaned)
        for record, pin in zip(records, pins):
            if pin:
                record._set_pin(pin)
        return records

    def write(self, vals):
        vals = dict(vals)
        pin = vals.pop("pin_plain", False)
        res = super().write(vals)
        if pin:
            for rec in self:
                rec._set_pin(pin)
        return res

    def _set_pin(self, pin):
        self.ensure_one()
        pin = str(pin or "").strip()
        if not pin.isdigit() or not (4 <= len(pin) <= 12):
            raise ValidationError(_("Die PIN muss aus 4 bis 12 Ziffern bestehen."))
        duplicate = self.search([("id", "!=", self.id), ("active", "=", True)])
        for person in duplicate:
            if person._check_pin(pin):
                raise ValidationError(_("Diese PIN ist bereits einer anderen aktiven Person zugeordnet."))
        salt = secrets.token_hex(16)
        digest = self._hash_pin(pin, salt)
        super(GlMediaApprovalPerson, self).write({"pin_salt": salt, "pin_hash": digest})

    @staticmethod
    def _hash_pin(pin, salt):
        return hashlib.pbkdf2_hmac("sha256", str(pin).encode("utf-8"), str(salt).encode("utf-8"), 200000).hex()

    def _check_pin(self, pin):
        self.ensure_one()
        if not self.pin_hash or not self.pin_salt:
            return False
        digest = self._hash_pin(pin, self.pin_salt)
        return hmac.compare_digest(digest, self.pin_hash)

    @api.model
    def authenticate_pin(self, pin):
        pin = str(pin or "").strip()
        if not pin:
            return self.browse()
        for person in self.sudo().search([("active", "=", True)]):
            if person._check_pin(pin):
                return person
        return self.browse()
