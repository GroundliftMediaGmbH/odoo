# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class GlSocialPostRegenerateWizard(models.TransientModel):
    _name = 'gl.social.post.regenerate.wizard'
    _description = 'Groundlift Social Post neu generieren'

    post_id = fields.Many2one('social.post', string='Social Post', required=True, ondelete='cascade')
    focal_x = fields.Selection([
        ('left', 'Links'),
        ('center', 'Mitte'),
        ('right', 'Rechts'),
    ], string='Horizontaler Fokus', default='center')
    focal_y = fields.Selection([
        ('top', 'Oben'),
        ('center', 'Mitte'),
        ('bottom', 'Unten'),
    ], string='Vertikaler Fokus', default='center')

    def action_apply(self):
        self.ensure_one()
        post = self.post_id
        attachments = post._gl_image_attachments()
        if not attachments:
            raise UserError('Dieser Social Post hat kein Bild, das angepasst werden kann.')
        source = attachments[0]
        new_attachment = post._gl_crop_attachment_to_target(source, focal_x=self.focal_x, focal_y=self.focal_y)
        post._gl_replace_image_attachments(new_attachment)
        post.write({
            'gl_adjust_image_crop': True,
            'gl_requires_approval': True,
            'gl_approved': False,
        })
        post._gl_force_draft_if_possible()
        post._gl_update_image_aspect_status()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Social Post',
            'res_model': 'social.post',
            'view_mode': 'form',
            'res_id': post.id,
            'target': 'current',
        }
