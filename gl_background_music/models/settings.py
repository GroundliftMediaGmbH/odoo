# -*- coding: utf-8 -*-
import secrets

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    gl_music_client_id = fields.Char(
        string="Spotify Client ID", config_parameter="gl_music.client_id")
    gl_music_client_secret = fields.Char(
        string="Spotify Client Secret", config_parameter="gl_music.client_secret")
    gl_music_redirect_uri = fields.Char(
        string="Exakte Spotify Redirect URI", config_parameter="gl_music.redirect_uri",
        help="HTTPS-Adresse dieser Odoo-Datenbank mit /gl_music/spotify/callback; exakt bei Spotify hinterlegen.")
    gl_music_device_name = fields.Char(
        string="Spotify-Connect-Gerätename", config_parameter="gl_music.device_name",
        help="Wird gegen den von Spotify gemeldeten Gerätenamen geprüft. Keine automatische Umschaltung auf andere Geräte.")
    gl_music_agent_key = fields.Char(
        string="Windows-Verbindungsschlüssel", config_parameter="gl_music.agent_key",
        help="Diesen Schlüssel nur am Wiedergabe-PC eingeben. Nach Wechsel muss dieser erneut gekoppelt werden.")

    def action_gl_music_regenerate_agent_key(self):
        self.ensure_one()
        self.env["ir.config_parameter"].sudo().set_param(
            "gl_music.agent_key", secrets.token_urlsafe(36))
        return {
            "type": "ir.actions.act_window",
            "name": "Hintergrundmusik – Einrichtung",
            "res_model": "res.config.settings",
            "view_mode": "form",
            "target": "inline",
            "context": {"module": "gl_background_music"},
        }
