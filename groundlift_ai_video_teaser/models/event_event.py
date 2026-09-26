from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .video_job import _as_bool


class EventEvent(models.Model):
    _inherit = 'event.event'

    gl_video_asset_ids = fields.One2many('gl.video.teaser.asset', 'event_id', string='Video-Assets')
    gl_video_job_ids = fields.One2many('gl.video.teaser.job', 'event_id', string='Video-Teaser')
    gl_video_job_count = fields.Integer(compute='_compute_gl_video_job_count')
    gl_video_latest_job_id = fields.Many2one('gl.video.teaser.job', copy=False, string='Freigegebener Video-Teaser')
    gl_video_teaser_16_9_url = fields.Char(related='gl_video_latest_job_id.output_url_16_9', readonly=True)
    gl_video_teaser_9_16_url = fields.Char(related='gl_video_latest_job_id.output_url_9_16', readonly=True)

    @api.depends('gl_video_job_ids')
    def _compute_gl_video_job_count(self):
        for rec in self:
            rec.gl_video_job_count = len(rec.gl_video_job_ids)

    def action_create_ai_video_teaser(self):
        self.ensure_one()
        self._gl_video_auto_import_event_image()
        style = self.env['gl.video.teaser.style'].search([('active', '=', True)], order='sequence, id', limit=1)
        if not style:
            raise UserError(_('Es ist kein aktiver Video-Style angelegt.'))
        icp = self.env['ir.config_parameter'].sudo()
        job = self.env['gl.video.teaser.job'].create({
            'event_id': self.id,
            'style_id': style.id,
            'duration': 20,
            'generate_16_9': True,
            'generate_9_16': True,
            'generate_music': _as_bool(icp.get_param('gl_ai_video.generate_music'), True),
            'use_runway': True,
            'subtitles': True,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('AI Video-Teaser'),
            'res_model': 'gl.video.teaser.job',
            'res_id': job.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_ai_video_teasers(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Video-Teaser'),
            'res_model': 'gl.video.teaser.job',
            'view_mode': 'list,form',
            'domain': [('event_id', '=', self.id)],
            'context': {'default_event_id': self.id},
        }

    def _gl_video_auto_import_event_image(self):
        self.ensure_one()
        if self.gl_video_asset_ids.filtered(lambda a: a.role == 'event_image'):
            return
        icp = self.env['ir.config_parameter'].sudo()
        configured = (icp.get_param('gl_ai_video.event_image_field') or '').strip()
        candidates = [configured] if configured else []
        if 'image_1920' not in candidates:
            candidates.append('image_1920')
        for field_name in candidates:
            if not field_name or field_name not in self._fields:
                continue
            field = self._fields[field_name]
            value = self[field_name]
            if not value:
                continue
            vals = {
                'event_id': self.id,
                'name': f'{self.name} · Eventbild',
                'role': 'event_image',
                'asset_type': 'image',
                'priority': 20,
                'ai_motion_allowed': True,
            }
            if field.type == 'binary':
                vals.update({'source_type': 'upload', 'file_data': value, 'filename': f'event_{self.id}.jpg'})
            elif field.type in ('char', 'text') and str(value).startswith(('http://', 'https://')):
                vals.update({'source_type': 'url', 'external_url': value})
            else:
                continue
            self.env['gl.video.teaser.asset'].create(vals)
            return
