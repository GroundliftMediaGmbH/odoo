# -*- coding: utf-8 -*-
import uuid

from markupsafe import Markup, escape

from odoo import _, api, fields, models


ANNOUNCED_STAGE_NAME = 'angekündigt'


class EventEvent(models.Model):
    _inherit = 'event.event'

    artist_portal_access_token = fields.Char(
        string='Künstlerportal-Zugriffstoken',
        default=lambda self: uuid.uuid4().hex,
        copy=False,
        readonly=True,
    )
    artist_portal_available = fields.Boolean(
        string='Künstlerportal aktiv',
        compute='_compute_artist_portal_access',
        readonly=True,
    )
    artist_portal_url = fields.Char(
        string='Künstler-/Agenturportal',
        compute='_compute_artist_portal_access',
        readonly=True,
    )
    artist_portal_status = fields.Char(
        string='Portalstatus',
        compute='_compute_artist_portal_access',
        readonly=True,
    )
    artist_portal_qr_html = fields.Html(
        string='Künstlerportal QR-Code',
        compute='_compute_artist_portal_qr_html',
        sanitize=False,
        readonly=True,
    )

    def _artist_portal_stage_names(self):
        """Return translated stage names that can reasonably identify the configured stage."""
        self.ensure_one()
        if not self.stage_id:
            return set()
        names = set()
        for lang in (self.env.lang, 'de_DE', 'en_US'):
            try:
                name = self.stage_id.with_context(lang=lang).name
            except Exception:
                name = self.stage_id.name
            if name:
                names.add(name.strip().casefold())
        return names

    def _is_artist_portal_stage(self):
        self.ensure_one()
        names = self._artist_portal_stage_names()
        return ANNOUNCED_STAGE_NAME in names or 'angekuendigt' in names

    @api.depends('stage_id', 'stage_id.name', 'artist_portal_access_token')
    def _compute_artist_portal_access(self):
        for event in self:
            enabled = bool(event.id and event.artist_portal_access_token and event._is_artist_portal_stage())
            event.artist_portal_available = enabled
            if enabled:
                event.artist_portal_url = '%s/event/artist/%s/%s' % (
                    event.get_base_url().rstrip('/'),
                    event.id,
                    event.artist_portal_access_token,
                )
                event.artist_portal_status = _('Aktiv – die Veranstaltung ist in der Phase „Angekündigt“.')
            else:
                event.artist_portal_url = False
                event.artist_portal_status = _('Nicht aktiv – das Portal ist nur in der Phase „Angekündigt“ erreichbar.')

    @api.depends('artist_portal_url')
    def _compute_artist_portal_qr_html(self):
        for event in self:
            if not event.artist_portal_url:
                event.artist_portal_qr_html = Markup(
                    '<span class="text-muted">QR-Code wird angezeigt, sobald die Veranstaltung in der Phase „Angekündigt“ ist.</span>'
                )
                continue
            from urllib.parse import quote
            qr_src = '/report/barcode/QR/%s?width=220&height=220&humanreadable=0' % quote(
                event.artist_portal_url, safe=''
            )
            event.artist_portal_qr_html = Markup(
                '<div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;">'
                '<img src="%s" alt="Künstlerportal QR-Code" '
                'style="width:160px;height:160px;border:1px solid #ddd;border-radius:12px;padding:8px;background:#fff;"/>'
                '<div><strong>Künstler-/Agenturportal</strong><br/>'
                '<span class="text-muted">Link oder QR-Code an Künstler bzw. Agentur weitergeben.</span><br/>'
                '<small style="word-break:break-all;">%s</small></div>'
                '</div>'
            ) % (escape(qr_src), escape(event.artist_portal_url))

    @api.model
    def _ensure_artist_portal_tokens(self):
        events = self.sudo().with_context(active_test=False).search([
            ('artist_portal_access_token', '=', False),
        ])
        for event in events:
            event.write({'artist_portal_access_token': uuid.uuid4().hex})
        return True

    def action_regenerate_artist_portal_token(self):
        for event in self:
            event.artist_portal_access_token = uuid.uuid4().hex
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Künstler-/Agenturportal'),
                'message': _('Der Zugriffslink wurde neu erzeugt. Der bisherige Link ist ab sofort ungültig.'),
                'type': 'warning',
                'sticky': False,
            },
        }


class GuestlistLine(models.Model):
    _inherit = 'gl.event.guestlist.line'

    artist_portal_entry_type = fields.Selection(
        [
            ('guestlist', 'Künstlerportal: Gästeliste'),
            ('box_office', 'Künstlerportal: Abendkasse'),
        ],
        string='Künstlerportal-Art',
        copy=False,
        readonly=True,
    )
    artist_portal_created = fields.Boolean(
        string='Über Künstlerportal eingetragen',
        default=False,
        copy=False,
        readonly=True,
    )
    artist_portal_submitted_by = fields.Char(
        string='Künstler/Agentur Ansprechpartner',
        copy=False,
        readonly=True,
    )
