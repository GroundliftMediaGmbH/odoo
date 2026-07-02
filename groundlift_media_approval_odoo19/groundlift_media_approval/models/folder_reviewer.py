# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class GlMediaApprovalFolderReviewer(models.Model):
    _name = "gl.media.approval.folder.reviewer"
    _description = "Medienfreigabe Ordner-Bewerter"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    folder_id = fields.Many2one(
        "gl.media.approval.folder",
        required=True,
        ondelete="cascade",
        index=True,
    )
    person_id = fields.Many2one(
        "gl.media.approval.person",
        string="Bestehende Person",
        ondelete="restrict",
        domain="[('active', '=', True)]",
        help="Optional: bestehende Person auswählen. Wenn leer, wird aus Name + PIN automatisch eine Person angelegt.",
    )
    name = fields.Char(string="Name")
    pin_code = fields.Char(string="6-stellige PIN", size=6)
    email = fields.Char(string="E-Mail")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "folder_person_uniq",
            "unique(folder_id, person_id)",
            "Diese Person ist in diesem Unterordner bereits als Bewerter hinterlegt.",
        ),
    ]

    @api.onchange("person_id")
    def _onchange_person_id(self):
        for rec in self:
            if rec.person_id:
                rec.name = rec.person_id.name
                rec.pin_code = rec.person_id.pin_code
                rec.email = rec.person_id.email
                rec.active = rec.person_id.active

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        Person = self.env["gl.media.approval.person"].sudo()
        for vals in vals_list:
            vals = dict(vals)
            if vals.get("person_id"):
                person = Person.browse(int(vals["person_id"]))
                if person.exists():
                    vals.setdefault("name", person.name)
                    vals.setdefault("pin_code", person.pin_code)
                    vals.setdefault("email", person.email)
                    vals.setdefault("active", person.active)
            if vals.get("pin_code"):
                vals["pin_code"] = str(vals.get("pin_code")).strip()
            prepared.append(vals)
        records = super().create(prepared)
        records._ensure_persons()
        records.mapped("folder_id")._sync_reviewer_person_ids_from_lines()
        return records

    def write(self, vals):
        vals = dict(vals)
        if vals.get("pin_code"):
            vals["pin_code"] = str(vals.get("pin_code")).strip()
        res = super().write(vals)
        self._ensure_persons()
        self.mapped("folder_id")._sync_reviewer_person_ids_from_lines()
        return res

    def unlink(self):
        folders = self.mapped("folder_id")
        res = super().unlink()
        folders._sync_reviewer_person_ids_from_lines()
        return res

    def _ensure_persons(self):
        Person = self.env["gl.media.approval.person"].sudo()
        for rec in self.sudo():
            if not rec.active:
                continue
            if rec.person_id and (not rec.name or not rec.pin_code):
                super(GlMediaApprovalFolderReviewer, rec).write({
                    "name": rec.name or rec.person_id.name,
                    "pin_code": rec.pin_code or rec.person_id.pin_code,
                    "email": rec.email or rec.person_id.email,
                })
            pin = str(rec.pin_code or "").strip()
            name = (rec.name or "").strip()
            if not name:
                raise ValidationError(_("Bitte bei jedem Bewerter einen Namen eintragen."))
            if not pin or not pin.isdigit() or len(pin) != 6:
                raise ValidationError(_("Die PIN muss genau aus 6 Ziffern bestehen."))

            if rec.person_id:
                # Bestehende Person synchronisieren. Die eindeutige PIN-Prüfung liegt im Personenmodell.
                rec.person_id.write({
                    "name": name,
                    "pin_code": pin,
                    "email": rec.email or False,
                    "active": bool(rec.active),
                })
                continue

            person = Person.search([("pin_code", "=", pin), ("active", "=", True)], limit=1)
            if not person:
                person = Person.search([("name", "=", name)], limit=1)
            if person:
                person.write({
                    "name": name,
                    "pin_code": pin,
                    "email": rec.email or person.email or False,
                    "active": True,
                })
            else:
                person = Person.create({
                    "name": name,
                    "pin_code": pin,
                    "email": rec.email or False,
                    "active": True,
                })
            super(GlMediaApprovalFolderReviewer, rec).write({"person_id": person.id})

    @api.constrains("pin_code", "active")
    def _check_pin_code(self):
        for rec in self:
            if not rec.active:
                continue
            pin = str(rec.pin_code or "").strip()
            if not pin.isdigit() or len(pin) != 6:
                raise ValidationError(_("Die PIN muss genau aus 6 Ziffern bestehen."))
