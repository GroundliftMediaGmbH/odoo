import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Branding: stored on company so multi-company setups remain clean.
    gl_video_brand_name = fields.Char(related='company_id.gl_video_brand_name', readonly=False)
    gl_video_outro_claim = fields.Char(related='company_id.gl_video_outro_claim', readonly=False)
    gl_video_cta = fields.Char(related='company_id.gl_video_cta', readonly=False)
    gl_video_footer = fields.Char(related='company_id.gl_video_footer', readonly=False)
    gl_video_location_phrase = fields.Char(related='company_id.gl_video_location_phrase', readonly=False)
    gl_video_hook_template = fields.Char(related='company_id.gl_video_hook_template', readonly=False)
    gl_video_brand_bg = fields.Char(related='company_id.gl_video_brand_bg', readonly=False)
    gl_video_brand_fg = fields.Char(related='company_id.gl_video_brand_fg', readonly=False)
    gl_video_brand_accent = fields.Char(related='company_id.gl_video_brand_accent', readonly=False)

    # OpenAI
    gl_video_openai_api_key = fields.Char(config_parameter='gl_ai_video.openai_api_key')
    gl_video_openai_model = fields.Char(config_parameter='gl_ai_video.openai_model', default='gpt-5.6-terra')
    gl_video_openai_reasoning = fields.Selection(
        [('none', 'none'), ('low', 'low'), ('medium', 'medium'), ('high', 'high')],
        config_parameter='gl_ai_video.openai_reasoning', default='medium',
    )

    # Runway
    gl_video_runway_api_key = fields.Char(config_parameter='gl_ai_video.runway_api_key')
    gl_video_runway_model = fields.Char(config_parameter='gl_ai_video.runway_model', default='gen4.5')
    gl_video_runway_clip_duration = fields.Integer(config_parameter='gl_ai_video.runway_clip_duration', default=5)
    gl_video_runway_max_clips = fields.Integer(config_parameter='gl_ai_video.runway_max_clips', default=3)
    gl_video_runway_generate_both = fields.Boolean(config_parameter='gl_ai_video.runway_generate_both', default=True)

    # ElevenLabs
    gl_video_eleven_api_key = fields.Char(config_parameter='gl_ai_video.eleven_api_key')
    gl_video_eleven_voice_id = fields.Char(config_parameter='gl_ai_video.eleven_voice_id')
    gl_video_eleven_tts_model = fields.Char(config_parameter='gl_ai_video.eleven_tts_model', default='eleven_multilingual_v2')
    gl_video_generate_music = fields.Boolean(config_parameter='gl_ai_video.generate_music', default=True)
    gl_video_eleven_music_model = fields.Char(config_parameter='gl_ai_video.eleven_music_model', default='music_v2_5')
    gl_video_music_volume = fields.Float(config_parameter='gl_ai_video.music_volume', default=18.0)

    # Creatomate
    gl_video_creatomate_api_key = fields.Char(config_parameter='gl_ai_video.creatomate_api_key')
    gl_video_creatomate_template_16_9 = fields.Char(config_parameter='gl_ai_video.creatomate_template_16_9')
    gl_video_creatomate_template_9_16 = fields.Char(config_parameter='gl_ai_video.creatomate_template_9_16')
    gl_video_use_templates = fields.Boolean(config_parameter='gl_ai_video.use_templates', default=False)
    gl_video_download_final = fields.Boolean(config_parameter='gl_ai_video.download_final', default=True)

    # Odoo field mapping / integration
    gl_video_short_description_field = fields.Char(config_parameter='gl_ai_video.short_description_field', default='description')
    gl_video_category_field = fields.Char(config_parameter='gl_ai_video.category_field', default='event_type_id')
    gl_video_ticket_url_field = fields.Char(config_parameter='gl_ai_video.ticket_url_field', default='website_url')
    gl_video_event_image_field = fields.Char(config_parameter='gl_ai_video.event_image_field', default='')
    gl_video_approval_webhook_url = fields.Char(config_parameter='gl_ai_video.approval_webhook_url')
    gl_video_batch_size = fields.Integer(config_parameter='gl_ai_video.batch_size', default=4)

    def action_test_video_providers(self):
        self.ensure_one()
        self.set_values()
        icp = self.env['ir.config_parameter'].sudo()
        results = []

        openai_key = icp.get_param('gl_ai_video.openai_api_key')
        if openai_key:
            r = requests.get('https://api.openai.com/v1/models', headers={'Authorization': f'Bearer {openai_key}'}, timeout=20)
            results.append(f"OpenAI: {'OK' if r.ok else 'Fehler ' + str(r.status_code)}")
        else:
            results.append('OpenAI: kein API-Key')

        eleven_key = icp.get_param('gl_ai_video.eleven_api_key')
        if eleven_key:
            r = requests.get('https://api.elevenlabs.io/v1/user/subscription', headers={'xi-api-key': eleven_key}, timeout=20)
            results.append(f"ElevenLabs: {'OK' if r.ok else 'Fehler ' + str(r.status_code)}")
        else:
            results.append('ElevenLabs: kein API-Key')

        creatomate_key = icp.get_param('gl_ai_video.creatomate_api_key')
        if creatomate_key:
            r = requests.get('https://api.creatomate.com/v2/templates', headers={'Authorization': f'Bearer {creatomate_key}'}, timeout=20)
            results.append(f"Creatomate: {'OK' if r.ok else 'Fehler ' + str(r.status_code)}")
        else:
            results.append('Creatomate: kein API-Key')

        runway_key = icp.get_param('gl_ai_video.runway_api_key')
        results.append('Runway: API-Key hinterlegt' if runway_key else 'Runway: kein API-Key')

        raise UserError('\n'.join(results))
