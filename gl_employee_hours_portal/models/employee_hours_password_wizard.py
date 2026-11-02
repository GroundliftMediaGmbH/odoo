# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class GlEmployeeHoursPasswordWizard(models.TransientModel):
    _name = "gl.employee.hours.password.wizard"
    _description = "Passwort für Mitarbeiter-Stundenportal setzen"
    _transient_max_hours = 0.1

    account_id = fields.Many2one(
        "gl.employee.hours.account", string="Stundenportal-Konto",
        required=True, readonly=True, ondelete="cascade",
    )
    new_password = fields.Char(string="Neues Passwort", required=True)
    confirm_password = fields.Char(string="Passwort wiederholen", required=True)

    def action_save_password(self):
        self.ensure_one()
        # Die Gruppenprüfung MUSS vor dem sudo() auf das Konto erfolgen.
        self.account_id._check_credential_manager()
        if self.new_password != self.confirm_password:
            raise UserError(_("Die beiden Passwörter stimmen nicht überein."))
        self.account_id.sudo().set_password(self.new_password)
        # Temporäre Klartextfelder unmittelbar nach erfolgreicher Änderung entfernen.
        self.sudo().unlink()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Passwort aktualisiert"),
                "message": _("Das Stundenportal-Passwort wurde geändert. Bisherige Stundenportal-Sitzungen wurden abgemeldet."),
                "type": "success",
            },
        }
