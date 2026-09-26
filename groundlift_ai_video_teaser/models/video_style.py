from odoo import fields, models


class GlVideoTeaserStyle(models.Model):
    _name = 'gl.video.teaser.style'
    _description = 'Groundlift Video Teaser Style'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    description = fields.Text()
    director_prompt = fields.Text(required=True)
    runway_prompt_suffix = fields.Text()
    music_prompt = fields.Text()
    subtitle_effect = fields.Selection([
        ('highlight', 'Highlight'),
        ('karaoke', 'Karaoke'),
        ('current_word', 'Current word'),
    ], default='highlight')

    template_kind = fields.Selection([
        ('performer_trailer', 'Performer / Einzel-Event'),
        ('multi_event_overview', 'Mehrere Veranstaltungen / Übersicht'),
    ], default='performer_trailer', required=True)
    pacing_profile = fields.Selection([
        ('fast', 'Schnell'),
        ('mixed', 'Gemischt'),
        ('calm', 'Ruhig'),
    ], default='mixed', required=True)
    target_scene_count = fields.Integer(default=4)
    min_scene_duration = fields.Float(default=1.5)
    max_scene_duration = fields.Float(default=6.0)
    reference_structure = fields.Text()
    identity_prompt = fields.Text()

    _sql_constraints = [
        ('gl_video_style_code_uniq', 'unique(code)', 'Der Style-Code muss eindeutig sein.'),
    ]
