import json
import logging

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Branding: stored on company so multi-company setups remain clean.
    gl_video_brand_name = fields.Char(string='Markenname', related='company_id.gl_video_brand_name', readonly=False)
    gl_video_outro_claim = fields.Char(string='Outro-Claim', related='company_id.gl_video_outro_claim', readonly=False)
    gl_video_cta = fields.Char(string='Call-to-Action', related='company_id.gl_video_cta', readonly=False)
    gl_video_footer = fields.Char(string='Footer / Website', related='company_id.gl_video_footer', readonly=False)
    gl_video_location_phrase = fields.Char(string='Ortsformulierung', related='company_id.gl_video_location_phrase', readonly=False)
    gl_video_hook_template = fields.Char(string='Hook-Vorlage', related='company_id.gl_video_hook_template', readonly=False)
    gl_video_brand_bg = fields.Char(string='Hintergrundfarbe', related='company_id.gl_video_brand_bg', readonly=False)
    gl_video_brand_fg = fields.Char(string='Textfarbe', related='company_id.gl_video_brand_fg', readonly=False)
    gl_video_brand_accent = fields.Char(string='Akzentfarbe', related='company_id.gl_video_brand_accent', readonly=False)

    # OpenAI
    gl_video_openai_api_key = fields.Char(string='OpenAI API-Key', config_parameter='gl_ai_video.openai_api_key')
    gl_video_openai_model = fields.Char(string='OpenAI Modell', config_parameter='gl_ai_video.openai_model', default='gpt-5.6-terra')
    gl_video_openai_reasoning = fields.Selection(
        [('none', 'none'), ('low', 'low'), ('medium', 'medium'), ('high', 'high')],
        string='Reasoning', config_parameter='gl_ai_video.openai_reasoning', default='medium',
    )

    # Runway
    gl_video_runway_api_key = fields.Char(string='Runway API-Key', config_parameter='gl_ai_video.runway_api_key')
    gl_video_runway_model = fields.Char(string='Runway Modell', config_parameter='gl_ai_video.runway_model', default='gen4.5')
    gl_video_runway_clip_duration = fields.Integer(string='Clip-Dauer (Sek.)', config_parameter='gl_ai_video.runway_clip_duration', default=5)
    gl_video_runway_max_clips = fields.Integer(string='Max. KI-Clips', config_parameter='gl_ai_video.runway_max_clips', default=3)
    gl_video_runway_generate_both = fields.Boolean(string='Beide Formate separat erzeugen', config_parameter='gl_ai_video.runway_generate_both', default=True)

    # ElevenLabs
    gl_video_eleven_api_key = fields.Char(string='ElevenLabs API-Key', config_parameter='gl_ai_video.eleven_api_key')
    gl_video_eleven_voice_id = fields.Char(string='Voice-ID', config_parameter='gl_ai_video.eleven_voice_id')
    gl_video_eleven_tts_model = fields.Char(string='TTS-Modell', config_parameter='gl_ai_video.eleven_tts_model', default='eleven_multilingual_v2')
    gl_video_generate_music = fields.Boolean(string='Musik automatisch erzeugen', config_parameter='gl_ai_video.generate_music', default=True)
    gl_video_eleven_music_model = fields.Char(string='Musik-Modell', config_parameter='gl_ai_video.eleven_music_model', default='music_v2_5')
    gl_video_music_volume = fields.Float(string='Musiklautstärke (%)', config_parameter='gl_ai_video.music_volume', default=18.0)

    # Creatomate
    gl_video_creatomate_api_key = fields.Char(string='Creatomate API-Key', config_parameter='gl_ai_video.creatomate_api_key')
    gl_video_creatomate_template_16_9 = fields.Char(string='Template-ID 16:9', config_parameter='gl_ai_video.creatomate_template_16_9')
    gl_video_creatomate_template_9_16 = fields.Char(string='Template-ID 9:16', config_parameter='gl_ai_video.creatomate_template_9_16')
    gl_video_use_templates = fields.Boolean(string='Eigene Creatomate-Templates verwenden', config_parameter='gl_ai_video.use_templates', default=False)
    gl_video_download_final = fields.Boolean(string='Finale Videos in Odoo speichern', config_parameter='gl_ai_video.download_final', default=True)

    # Odoo field mapping / integration
    gl_video_short_description_field = fields.Char(string='Feld: Kurzbeschreibung', config_parameter='gl_ai_video.short_description_field', default='description')
    gl_video_category_field = fields.Char(string='Feld: Kategorie', config_parameter='gl_ai_video.category_field', default='event_type_id')
    gl_video_ticket_url_field = fields.Char(string='Feld: Ticket-URL', config_parameter='gl_ai_video.ticket_url_field', default='website_url')
    gl_video_event_image_field = fields.Char(string='Feld: Eventbild', config_parameter='gl_ai_video.event_image_field', default='')
    gl_video_approval_webhook_url = fields.Char(string='Freigabe-Webhook URL', config_parameter='gl_ai_video.approval_webhook_url')
    gl_video_batch_size = fields.Integer(string='Jobs pro Cron-Lauf', config_parameter='gl_ai_video.batch_size', default=4)

    # Creative guardrails / reference editing blueprint
    gl_video_preserve_identity = fields.Boolean(string='Gesichter/Identität strikt bewahren', config_parameter='gl_ai_video.preserve_identity', default=True)
    gl_video_identity_guard_prompt = fields.Text(string='Identity-Guard Prompt', config_parameter='gl_ai_video.identity_guard_prompt', default='When a source image or video shows a real person, preserve that person exactly. Do not change face, body shape, age, hairstyle, skin tone, clothing identity, or proportions. Only add subtle camera motion, depth, lighting atmosphere, or gentle environmental movement. Never morph, swap, beautify, lip-sync, or re-cast a person.')
    gl_video_reference_blueprint = fields.Text(string='Referenz-Blueprint', config_parameter='gl_ai_video.reference_blueprint', default='Reference structure inspired by Groundlift sample teasers: 0-2 s strong hook or hero shot; 2-6 s protagonist / act reveal; 6-12 s quick montage of performers, venue or category highlights; 12-17 s key event promise plus date/location; final 3 s deterministic Groundlift CTA/outro. Text on screen remains short. Cuts feel modern and rhythmic, with sparse overlays and a clean final information card.')

    def action_save_video_settings(self):
        """Persist the dedicated AI-video settings form without leaving the app.

        res.config.settings is transient.  Odoo's generic execute() does persist
        config_parameter fields, but using an explicit action here makes the
        dedicated settings screen independent from the global Settings app and
        gives the user a clear success message.
        """
        self.ensure_one()
        self.set_values()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('AI Video Einstellungen'),
                'message': _('Die Einstellungen und API-Keys wurden gespeichert.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_test_video_providers(self):
        self.ensure_one()
        # Persist the form first.  Do not raise an exception afterwards: an
        # exception would roll back this transaction and therefore also discard
        # freshly entered API keys.
        self.set_values()
        icp = self.env['ir.config_parameter'].sudo()
        results = []

        def _check(label, url, headers):
            try:
                response = requests.get(url, headers=headers, timeout=20)
                if response.ok:
                    results.append(f"{label}: OK")
                else:
                    results.append(f"{label}: Fehler {response.status_code}")
            except requests.RequestException as exc:
                _logger.warning("AI video provider test failed for %s: %s", label, exc)
                results.append(f"{label}: Verbindung fehlgeschlagen")

        openai_key = icp.get_param('gl_ai_video.openai_api_key')
        if openai_key:
            _check('OpenAI', 'https://api.openai.com/v1/models', {'Authorization': f'Bearer {openai_key}'})
        else:
            results.append('OpenAI: kein API-Key')

        eleven_key = icp.get_param('gl_ai_video.eleven_api_key')
        if eleven_key:
            _check('ElevenLabs', 'https://api.elevenlabs.io/v1/user/subscription', {'xi-api-key': eleven_key})
        else:
            results.append('ElevenLabs: kein API-Key')

        creatomate_key = icp.get_param('gl_ai_video.creatomate_api_key')
        if creatomate_key:
            _check('Creatomate', 'https://api.creatomate.com/v2/templates', {'Authorization': f'Bearer {creatomate_key}'})
        else:
            results.append('Creatomate: kein API-Key')

        runway_key = icp.get_param('gl_ai_video.runway_api_key')
        results.append('Runway: API-Key hinterlegt' if runway_key else 'Runway: kein API-Key')

        has_error = any(
            ('Fehler' in result) or ('fehlgeschlagen' in result) or ('kein API-Key' in result)
            for result in results
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Provider-Prüfung'),
                'message': '\n'.join(results),
                'type': 'warning' if has_error else 'success',
                'sticky': True,
            },
        }

