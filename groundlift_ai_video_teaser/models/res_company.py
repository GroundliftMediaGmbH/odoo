import uuid

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    gl_video_brand_name = fields.Char(default='GROUNDLIFT')
    gl_video_outro_claim = fields.Char(default='Creative World')
    gl_video_cta = fields.Char(default='Jetzt Tickets sichern')
    gl_video_footer = fields.Char(default='groundlift.de')
    gl_video_location_phrase = fields.Char(default='im Groundlift am Ammersee')
    gl_video_hook_template = fields.Char(default='Am {date} {location} …')
    gl_video_brand_bg = fields.Char(default='#0B0B0B')
    gl_video_brand_fg = fields.Char(default='#FFFFFF')
    gl_video_brand_accent = fields.Char(default='#FFFFFF')
    gl_video_logo_token = fields.Char(default=lambda self: uuid.uuid4().hex, copy=False)
