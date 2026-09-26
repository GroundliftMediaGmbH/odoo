import json
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    _CONFIG_PARAMETER_FIELDS = {
        'gl_video_openai_api_key': 'gl_ai_video.openai_api_key',
        'gl_video_openai_model': 'gl_ai_video.openai_model',
        'gl_video_openai_reasoning': 'gl_ai_video.openai_reasoning',
        'gl_video_runway_api_key': 'gl_ai_video.runway_api_key',
        'gl_video_runway_model': 'gl_ai_video.runway_model',
        'gl_video_runway_clip_duration': 'gl_ai_video.runway_clip_duration',
        'gl_video_runway_max_clips': 'gl_ai_video.runway_max_clips',
        'gl_video_runway_generate_both': 'gl_ai_video.runway_generate_both',
        'gl_video_eleven_api_key': 'gl_ai_video.eleven_api_key',
        'gl_video_eleven_voice_id': 'gl_ai_video.eleven_voice_id',
        'gl_video_eleven_tts_model': 'gl_ai_video.eleven_tts_model',
        'gl_video_eleven_speed': 'gl_ai_video.eleven_speed',
        'gl_video_eleven_stability': 'gl_ai_video.eleven_stability',
        'gl_video_eleven_similarity': 'gl_ai_video.eleven_similarity',
        'gl_video_eleven_style': 'gl_ai_video.eleven_style',
        'gl_video_generate_music': 'gl_ai_video.generate_music',
        'gl_video_eleven_music_model': 'gl_ai_video.eleven_music_model',
        'gl_video_music_volume': 'gl_ai_video.music_volume',
        'gl_video_creatomate_api_key': 'gl_ai_video.creatomate_api_key',
        'gl_video_creatomate_template_16_9': 'gl_ai_video.creatomate_template_16_9',
        'gl_video_creatomate_template_9_16': 'gl_ai_video.creatomate_template_9_16',
        'gl_video_use_templates': 'gl_ai_video.use_templates',
        'gl_video_download_final': 'gl_ai_video.download_final',
        'gl_video_short_description_field': 'gl_ai_video.short_description_field',
        'gl_video_category_field': 'gl_ai_video.category_field',
        'gl_video_ticket_url_field': 'gl_ai_video.ticket_url_field',
        'gl_video_event_image_field': 'gl_ai_video.event_image_field',
        'gl_video_approval_webhook_url': 'gl_ai_video.approval_webhook_url',
        'gl_video_batch_size': 'gl_ai_video.batch_size',
        'gl_video_preserve_identity': 'gl_ai_video.preserve_identity',
    }

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
    gl_video_eleven_speed = fields.Float(string='Voice Speed', config_parameter='gl_ai_video.eleven_speed', default=1.12)
    gl_video_eleven_stability = fields.Float(string='Voice Stability', config_parameter='gl_ai_video.eleven_stability', default=0.30)
    gl_video_eleven_similarity = fields.Float(string='Voice Similarity', config_parameter='gl_ai_video.eleven_similarity', default=0.78)
    gl_video_eleven_style = fields.Float(string='Voice Style', config_parameter='gl_ai_video.eleven_style', default=0.48)
    gl_video_voice_direction = fields.Text(string='Voiceover-Regie', related='company_id.gl_video_voice_direction', readonly=False)
    gl_video_generate_music = fields.Boolean(string='Musik automatisch erzeugen', config_parameter='gl_ai_video.generate_music', default=True)
    gl_video_eleven_music_model = fields.Char(string='Musik-Modell', config_parameter='gl_ai_video.eleven_music_model', default='music_v2_5')
    gl_video_music_start_prompt = fields.Text(string='Musik-Startvorgabe', related='company_id.gl_video_music_start_prompt', readonly=False)
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
    gl_video_identity_guard_prompt = fields.Text(string='Identity-Guard Prompt', related='company_id.gl_video_identity_guard_prompt', readonly=False)
    gl_video_reference_blueprint = fields.Text(string='Referenz-Blueprint', related='company_id.gl_video_reference_blueprint', readonly=False)

    def _persist_company_fields(self):
        """Persist every company-scoped setting explicitly.

        The dedicated settings screen is a custom res.config.settings form.
        Writing all company-related fields in one operation makes persistence
        independent from inverse timing of related fields and keeps multi-company
        values deterministic.
        """
        self.ensure_one()
        self.company_id.sudo().write({
            'gl_video_brand_name': self.gl_video_brand_name or '',
            'gl_video_outro_claim': self.gl_video_outro_claim or '',
            'gl_video_cta': self.gl_video_cta or '',
            'gl_video_footer': self.gl_video_footer or '',
            'gl_video_location_phrase': self.gl_video_location_phrase or '',
            'gl_video_hook_template': self.gl_video_hook_template or '',
            'gl_video_brand_bg': self.gl_video_brand_bg or '',
            'gl_video_brand_fg': self.gl_video_brand_fg or '',
            'gl_video_brand_accent': self.gl_video_brand_accent or '',
            'gl_video_identity_guard_prompt': self.gl_video_identity_guard_prompt or '',
            'gl_video_reference_blueprint': self.gl_video_reference_blueprint or '',
            'gl_video_voice_direction': self.gl_video_voice_direction or '',
            'gl_video_music_start_prompt': self.gl_video_music_start_prompt or '',
        })

    def _validate_video_settings(self):
        self.ensure_one()
        if not 0.7 <= self.gl_video_eleven_speed <= 1.2:
            raise ValidationError(_('Voice Speed muss zwischen 0,70 und 1,20 liegen.'))
        for field_name, label in (
            ('gl_video_eleven_stability', _('Voice Stability')),
            ('gl_video_eleven_similarity', _('Voice Similarity')),
            ('gl_video_eleven_style', _('Voice Style')),
        ):
            value = self[field_name]
            if not 0.0 <= value <= 1.0:
                raise ValidationError(_('%s muss zwischen 0,00 und 1,00 liegen.') % label)
        if not 0.0 <= self.gl_video_music_volume <= 100.0:
            raise ValidationError(_('Musiklautstärke muss zwischen 0 und 100 Prozent liegen.'))
        if self.gl_video_runway_clip_duration < 2 or self.gl_video_runway_clip_duration > 10:
            raise ValidationError(_('Runway Clip-Dauer muss zwischen 2 und 10 Sekunden liegen.'))
        if self.gl_video_runway_max_clips < 0:
            raise ValidationError(_('Max. KI-Clips darf nicht negativ sein.'))
        if self.gl_video_batch_size < 1 or self.gl_video_batch_size > 20:
            raise ValidationError(_('Jobs pro Cron-Lauf muss zwischen 1 und 20 liegen.'))

    def _persist_config_parameters_explicitly(self):
        """Persist every global setting deterministically.

        Odoo normally persists ``config_parameter`` fields through
        ``res.config.settings`` automatically.  The teaser app also exposes a
        dedicated settings form, and older cached/custom settings flows have
        shown inconsistent persistence for numeric values (notably the
        ElevenLabs speech speed).  Writing the complete map explicitly keeps
        Float, Integer and Boolean settings stable across both settings views.
        """
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        for field_name, parameter in self._CONFIG_PARAMETER_FIELDS.items():
            value = self[field_name]
            field = self._fields[field_name]
            if field.type == 'boolean':
                stored = 'True' if bool(value) else 'False'
            elif value in (False, None):
                stored = ''
            else:
                stored = str(value)
            icp.set_param(parameter, stored)

    def set_values(self):
        """Persist native Odoo settings and then enforce the teaser values."""
        self.ensure_one()
        self._validate_video_settings()
        self._persist_company_fields()
        result = super().set_values()
        self._persist_config_parameters_explicitly()
        return result

    def action_save_video_settings(self):
        """Compatibility action for older cached views; use native execute()."""
        self.ensure_one()
        return self.execute()

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

