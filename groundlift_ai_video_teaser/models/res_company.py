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

    # Long editable creative prompts are stored directly on the company.
    # This avoids res.config.settings/config_parameter limitations for Text fields
    # and keeps values naturally separated in multi-company databases.
    gl_video_identity_guard_prompt = fields.Text(
        default=(
            'When a source image or video shows a real person, preserve that person exactly. '
            'Do not change face, body shape, age, hairstyle, skin tone, clothing identity, or proportions. '
            'Only add subtle camera motion, depth, lighting atmosphere, or gentle environmental movement. '
            'Never morph, swap, beautify, lip-sync, or re-cast a person.'
        )
    )
    gl_video_reference_blueprint = fields.Text(
        default=(
            'Reference structure inspired by Groundlift sample teasers: 0-2 s real action hook whenever available; '
            '2-6 s protagonist or act reveal; 6-12 s varied montage of performers, venue and atmosphere without '
            'repeating the same motif; 12-17 s key event promise plus date/location; final 3 s deterministic '
            'Groundlift CTA/outro.'
        )
    )
    gl_video_voice_direction = fields.Text(
        default=(
            'Energetisch, direkt, modern und ticketverkaufsorientiert. Kurze Sätze, aktive Verben, keine behäbigen '
            'Pausen, keine langen Aufzählungen. Der Sprecher soll pushen, ohne nach klassischer Radiowerbung zu klingen.'
        )
    )
    gl_video_music_start_prompt = fields.Text(
        default=(
            'Music must be clearly audible from frame 0. Start immediately with the beat and musical bed at 0.00 seconds. '
            'No silence, no ambient pre-roll, no slow intro, no fade-in. Keep energy under the voice but present from the first frame.'
        )
    )
