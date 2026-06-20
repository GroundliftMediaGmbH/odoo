# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class GlSocialPostRegenerateWizard(models.TransientModel):
    _name = 'gl.social.post.regenerate.wizard'
    _description = 'Groundlift Social Post neu generieren'

    post_id = fields.Many2one('social.post', string='Social Post', required=True, ondelete='cascade')
    mode = fields.Selection([
        ('variant', 'Variante generieren'),
        ('add_info', 'Bestimmte Information hinzufügen'),
    ], string='Aktion', default='variant', required=True)
    extra_information = fields.Text(string='Zusatzinformation')

    def action_apply(self):
        self.ensure_one()
        if self.mode == 'add_info' and not (self.extra_information or '').strip():
            raise UserError('Bitte die Information eingeben, die ergänzt werden soll.')
        self.post_id._gl_regenerate_ai_text(mode=self.mode, extra_information=self.extra_information or '')
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
        ('event', 'Andere Veranstaltung auswählen'),
        ('gap_filler', 'Lückenfüller generieren'),
    ], string='Ersetzen mit', default='event', required=True)
    event_id = fields.Many2one('event.event', string='Neue Veranstaltung')
    post_type = fields.Selection([
        ('announcement', 'Erstankündigung'),
        ('reminder_3d', 'Reminder 3 Tage vorher'),
        ('event_day', 'Eventtag'),
        ('soldout', 'Ausverkauft'),
        ('event_day_soldout', 'Eventtag ausverkauft'),
        ('completed', 'Nachbericht'),
    ], string='Post-Typ', default='announcement')
    extra_information = fields.Text(string='Zusatzinformation / gewünschter Fokus')

    def action_apply(self):
        self.ensure_one()
        if self.replacement_mode == 'event':
            if not self.event_id:
                raise UserError('Bitte eine Veranstaltung auswählen.')
            self.post_id._gl_replace_with_event(self.event_id, post_type=self.post_type or 'announcement', extra_information=self.extra_information or '')
        else:
            self.post_id._gl_replace_with_gap_filler(extra_information=self.extra_information or '')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Social Post',
            'res_model': 'social.post',
            'view_mode': 'form',
            'res_id': self.post_id.id,
            'target': 'current',
        }


class GlSocialPostImageAdjustWizard(models.TransientModel):
    _name = 'gl.social.post.image.adjust.wizard'
    _description = 'Groundlift Social Bildformat anpassen'

    post_id = fields.Many2one('social.post', string='Social Post', required=True, ondelete='cascade')
    mode = fields.Selection([
        ('crop', 'Ausschnitt anpassen'),
        ('generative_fill', 'Generativ füllen'),
    ], string='Methode', default='crop', required=True)
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
    extra_instruction = fields.Text(
        string='Hinweis für generatives Füllen',
        help='Optional: z. B. „Bühnenhintergrund natürlich erweitern, keine Schrift hinzufügen“.'
    )

    def action_apply(self):
        self.ensure_one()
        post = self.post_id
        attachments = post._gl_image_attachments()
        if not attachments:
            raise UserError('Dieser Social Post hat kein Bild, das angepasst werden kann.')
        source = attachments[0]
        if self.mode == 'crop':
            new_attachment = post._gl_crop_attachment_to_target(source, focal_x=self.focal_x, focal_y=self.focal_y)
        else:
            config = self.env['gl.event.social.config'].get_config()
            new_attachment = config._gl_openai_expand_image_attachment(
                source,
                target_ratio=post._gl_target_aspect_ratio(),
                target_label=post._gl_target_aspect_label(),
                extra_instruction=self.extra_instruction or '',
            )
        post._gl_replace_image_attachments(new_attachment)
        post.write({
            'gl_adjust_image_crop': True,
            'gl_adjust_image_generative_fill': False,
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
