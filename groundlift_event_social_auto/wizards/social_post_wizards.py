# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class GlSocialPostRegenerateWizard(models.TransientModel):
    _name = 'gl.social.post.regenerate.wizard'
    _description = 'Groundlift Social Post neu generieren'

    post_id = fields.Many2one('social.post', string='Social Post', required=True, ondelete='cascade')
    mode = fields.Selection([
        ('variant', 'Neue Variante erzeugen'),
        ('add_info', 'Bestimmte Information hinzufügen'),
    ], string='Methode', default='variant', required=True)
    extra_information = fields.Text(string='Zusatzinformation')

    # Deprecated compatibility fields: kept so stale wizard views from older
    # builds do not crash during upgrades. They are no longer used by this
    # text-regeneration wizard.
    extra_instruction = fields.Text(string='Hinweis für generatives Füllen (deaktiviert)')
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
        if self.mode == 'add_info' and not (self.extra_information or '').strip():
            raise UserError('Bitte eine Zusatzinformation eintragen oder „Neue Variante erzeugen“ wählen.')
        self.post_id._gl_regenerate_ai_text(
            mode=self.mode or 'variant',
            extra_information=self.extra_information or '',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': 'Social Post',
            'res_model': 'social.post',
            'view_mode': 'form',
            'res_id': self.post_id.id,
            'target': 'current',
        }


class GlSocialPostReplaceWizard(models.TransientModel):
    _name = 'gl.social.post.replace.wizard'
    _description = 'Groundlift Social Post ersetzen'

    post_id = fields.Many2one('social.post', string='Social Post', required=True, ondelete='cascade')
    replacement_mode = fields.Selection([
        ('event', 'Mit Veranstaltung ersetzen'),
        ('gap_filler', 'Mit Lückenfüller ersetzen'),
    ], string='Ersetzen durch', default='event', required=True)
    event_id = fields.Many2one('event.event', string='Veranstaltung')
    post_type = fields.Selection([
        ('announcement', 'Erstankündigung'),
        ('reminder_3d', 'Reminder 3 Tage vorher'),
        ('event_day', 'Eventtag'),
        ('soldout', 'Ausverkauft'),
        ('event_day_soldout', 'Eventtag ausverkauft'),
        ('completed', 'Nachbericht'),
    ], string='Post-Typ', default='announcement', required=True)
    extra_information = fields.Text(string='Zusatzinformation')

    def action_apply(self):
        self.ensure_one()
        post = self.post_id
        if self.replacement_mode == 'event':
            if not self.event_id:
                raise UserError('Bitte eine Veranstaltung auswählen.')
            post._gl_replace_with_event(
                self.event_id,
                post_type=self.post_type or 'announcement',
                extra_information=self.extra_information or '',
            )
        else:
            post._gl_replace_with_gap_filler(extra_information=self.extra_information or '')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Social Post',
            'res_model': 'social.post',
            'view_mode': 'form',
            'res_id': post.id,
            'target': 'current',
        }


class GlSocialPostImageAdjustWizard(models.TransientModel):
    _name = 'gl.social.post.image.adjust.wizard'
    _description = 'Groundlift Social Post Bildformat anpassen'

    post_id = fields.Many2one('social.post', string='Social Post', required=True, ondelete='cascade')
    focal_x = fields.Selection([
        ('left', 'Links'),
        ('center', 'Mitte'),
        ('right', 'Rechts'),
    ], string='Horizontaler Fokus', default='center', required=True)
    focal_y = fields.Selection([
        ('top', 'Oben'),
        ('center', 'Mitte'),
        ('bottom', 'Unten'),
    ], string='Vertikaler Fokus', default='center', required=True)

    def action_apply(self):
        self.ensure_one()
        post = self.post_id
        attachments = post._gl_image_attachments()
        if not attachments:
            raise UserError('Dieser Social Post hat kein Bild, das angepasst werden kann.')
        adjusted = post.env['ir.attachment']
        for attachment in attachments:
            adjusted |= post._gl_crop_attachment_to_target(
                attachment,
                focal_x=self.focal_x or 'center',
                focal_y=self.focal_y or 'center',
            )
        if adjusted:
            post._gl_replace_multiple_image_attachments(adjusted)
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
