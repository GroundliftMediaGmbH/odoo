# -*- coding: utf-8 -*-
"""Curated Vimeo URLs for the Künstlerportal video pitch."""
import re
from urllib.parse import parse_qs, urlsplit

from odoo import api, fields, models

VIDEO_PITCH_HEADLINE = 'Du willst Dein Event wie viele bei uns aufzeichnen lassen? Hol´ Dir Appetit und melde Dich gerne bei uns!'
VIDEO_PITCH_EYEBROW = 'Live bei Groundlift'
VIDEO_PITCH_HEADLINE_PARAMETER = 'gl_event_artist_portal.video_pitch_headline'
VIDEO_PITCH_EYEBROW_PARAMETER = 'gl_event_artist_portal.video_pitch_eyebrow'

VIDEO_DEFAULTS = (
    ('https://player.vimeo.com/video/783241157?h=9ad2e52a02', 'Martin Schmitt'),
    ('https://player.vimeo.com/video/783243493?h=d770f44eec', "San2 Unplugged: You've Got a Friend – The Groundlift Stories"),
    ('https://player.vimeo.com/video/906287508?h=0220cf8333', 'Most Foul – Bublath-Trio'),
    ('https://player.vimeo.com/video/783238247?h=1bdf29dc13', 'Groundlift Band'),
)


def safe_vimeo_embed(raw):
    """Only an HTTPS Vimeo video id/hash may become an iframe URL.

    This deliberately does not accept HTML/iframe pasted from the web, and
    never renders an arbitrary host or arbitrary query parameters in an iframe.
    """
    raw = (raw or '').strip()
    if not raw or any(char.isspace() for char in raw):
        return False
    try:
        url = urlsplit(raw)
        if url.scheme != 'https' or url.username or url.password or url.port not in (None, 443):
            return False
        host = (url.hostname or '').lower()
        parts = [part for part in url.path.split('/') if part]
        if host == 'player.vimeo.com' and len(parts) == 2 and parts[0] == 'video':
            video_id = parts[1]
            path_hash = None
        elif host in ('vimeo.com', 'www.vimeo.com') and len(parts) in (1, 2):
            video_id = parts[0]
            path_hash = parts[1] if len(parts) == 2 else None
        else:
            return False
        if not re.fullmatch(r'[0-9]{3,15}', video_id):
            return False
        query_hash = parse_qs(url.query).get('h', [None])[0]
        digest = query_hash or path_hash
        if digest and not re.fullmatch(r'[a-fA-F0-9]{6,64}', digest):
            return False
        return ('https://player.vimeo.com/video/%s?h=%s&title=0&byline=0&portrait=0'
                % (video_id, digest)) if digest else (
                'https://player.vimeo.com/video/%s?title=0&byline=0&portrait=0' % video_id)
    except ValueError:
        return False


class ArtistPortalVideoConfig(models.AbstractModel):
    _name = 'gl.artist.portal.video.config'
    _description = 'Globale Künstlerportal-Videokonfiguration'

    @api.model
    def get_portal_videos(self):
        params = self.env['ir.config_parameter'].sudo()
        videos = []
        for number, (default_url, default_title) in enumerate(VIDEO_DEFAULTS, 1):
            src = safe_vimeo_embed(params.get_param(
                'gl_event_artist_portal.video_%d_url' % number, default=default_url))
            title = (params.get_param(
                'gl_event_artist_portal.video_%d_title' % number, default=default_title)
                or default_title).strip()[:140]
            if src:
                videos.append({'url': src, 'title': title})
        return videos

    @api.model
    def get_portal_pitch(self):
        """Global texts, read on every page load so changes apply to all events."""
        params = self.env['ir.config_parameter'].sudo()
        return {
            'headline': (params.get_param(
                VIDEO_PITCH_HEADLINE_PARAMETER, default=VIDEO_PITCH_HEADLINE)
                or VIDEO_PITCH_HEADLINE).strip(),
            'eyebrow': (params.get_param(
                VIDEO_PITCH_EYEBROW_PARAMETER, default=VIDEO_PITCH_EYEBROW)
                or VIDEO_PITCH_EYEBROW).strip(),
        }
