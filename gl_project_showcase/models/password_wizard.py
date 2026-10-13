from odoo import fields, models
from odoo.exceptions import AccessError
from odoo import _


class ShowcasePasswordWizard(models.TransientModel):
    _name = 'gl.showcase.password.wizard'
    _description = 'Neues Showcase-Passwort'

    showcase_id = fields.Many2one('gl.project.showcase', required=True, readonly=True)
    new_password = fields.Char(required=True, string='Neues Passwort')
    confirm_password = fields.Char(required=True, string='Wiederholen')

    def action_save(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_user'):
            raise AccessError(_('Keine Berechtigung.'))
        if self.new_password != self.confirm_password:
            from odoo.exceptions import ValidationError
            raise ValidationError(_('Die Passwörter stimmen nicht überein.'))
        self.showcase_id._set_new_password(self.new_password)
        return {'type': 'ir.actions.act_window_close'}
