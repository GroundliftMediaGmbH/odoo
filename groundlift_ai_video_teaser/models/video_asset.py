import mimetypes
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class GlVideoTeaserAsset(models.Model):
    _name = 'gl.video.teaser.asset'
    _description = 'Groundlift Video Teaser Asset'
    _order = 'priority, id'

    event_id = fields.Many2one('event.event', required=True, ondelete='cascade', index=True)
    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    priority = fields.Integer(default=10)
    role = fields.Selection([
        ('real_video', 'Echtes Kurzvideo'),
        ('social_graphic', 'Social-Grafik'),
        ('press_photo', 'Pressefoto'),
        ('event_image', 'Eventbild'),
        ('logo', 'Logo'),
        ('other', 'Sonstiges'),
    ], default='other', required=True)
    asset_type = fields.Selection([('image', 'Bild'), ('video', 'Video')], required=True, default='image')
    source_type = fields.Selection([('upload', 'Upload'), ('url', 'URL')], required=True, default='upload')
    file_data = fields.Binary(attachment=True)
    filename = fields.Char()
    mime_type = fields.Char(compute='_compute_mime_type', store=True)
    external_url = fields.Char()
    use_in_teaser = fields.Boolean(default=True)
    ai_motion_allowed = fields.Boolean(default=True)
    contains_people = fields.Boolean(string='Zeigt Personen / Gesichter', default=False)
    identity_lock = fields.Boolean(string='Identität strikt bewahren', default=True)
    notes = fields.Char()
    public_token = fields.Char(default=lambda self: uuid.uuid4().hex, copy=False, required=True)
    public_url = fields.Char(compute='_compute_public_url')

    @api.depends('filename', 'asset_type')
    def _compute_mime_type(self):
        for rec in self:
            guessed = mimetypes.guess_type(rec.filename or '')[0]
            rec.mime_type = guessed or ('video/mp4' if rec.asset_type == 'video' else 'image/jpeg')

    @api.depends('source_type', 'external_url', 'public_token')
    def _compute_public_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '').rstrip('/')
        for rec in self:
            if rec.source_type == 'url':
                rec.public_url = rec.external_url or False
            elif rec.id and rec.file_data:
                rec.public_url = f'{base}/gl_ai_video/asset/{rec.id}/{rec.public_token}'
            else:
                rec.public_url = False

    @api.constrains('source_type', 'external_url', 'file_data')
    def _check_source(self):
        for rec in self:
            if rec.source_type == 'url':
                if not rec.external_url:
                    raise ValidationError(_('Bei Quelle URL muss eine URL eingetragen sein.'))
                if not rec.external_url.lower().startswith('https://'):
                    raise ValidationError(_('Externe Video-Assets müssen per HTTPS erreichbar sein.'))
