# -*- coding: utf-8 -*-
"""Artist self-service documents, media, locks and invitation mail."""
import html
import logging
import os
import uuid
from lxml import etree

from odoo import _, api, fields, models
from odoo.tools import html2plaintext
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SHORT_FIELD = 'x_studio_event_kurzbeschreibung'
RIDER_FIELDS = {'tech': 'x_studio_tech_rider', 'hospitality': 'x_studio_hospitality_rider'}
MAX_IMAGE = 12 * 1024 * 1024
MAX_DOCUMENT = 20 * 1024 * 1024


class ArtistPhoto(models.Model):
    _name = 'gl.artist.portal.photo'
    _description = 'Künstlerportal-Pressefoto'
    _order = 'id asc'

    event_id = fields.Many2one('event.event', required=True, index=True, ondelete='cascade')
    format = fields.Selection([('square', 'Quadratisch 1:1'), ('landscape', 'Querformat'),
                               ('portrait', 'Hochformat')], required=True)
    image = fields.Binary(required=True, attachment=True, copy=False)
    filename = fields.Char(required=True)
    width = fields.Integer()
    height = fields.Integer()
    active = fields.Boolean(default=True)


class EventEvent(models.Model):
    _inherit = 'event.event'

    artist_portal_contract_contact_id = fields.Many2one(
        'res.partner', string='Vertrag: Künstler / Agentur (Portal-Einladung)', copy=False,
        help='Die Einladung geht an die E-Mail-Adresse dieses Kontakts. Im Staging nur an julius@groundlift.de.')
    artist_portal_introduction = fields.Text(
        string='Einladungstext Künstler-/Agenturportal',
        default='Liebe Künstlerinnen, Künstler und Agenturen,\n\n'
                'für die Veranstaltung {event} steht euch unser Groundlift-Portal zur Verfügung. '
                'Dort könnt ihr Tech- und Hospitality-Rider, Pressefotos und Pressetexte einreichen. '
                'Ab der Phase „Angekündigt“ könnt ihr außerdem die Gästeliste pflegen und Ticketstände ansehen.\n\n'
                'Euer persönlicher Link: {portal_url}\n\nViele Grüße\nEuer GROUNDLIFT-Team')
    artist_portal_invitation_sent_at = fields.Datetime(string='Portal-Einladung versendet', readonly=True, copy=False)
    artist_portal_invitation_recipient = fields.Char(string='Letzter Einladungsempfänger', readonly=True, copy=False)
    artist_portal_photo_ids = fields.One2many('gl.artist.portal.photo', 'event_id', string='Pressefotos')
    artist_portal_short_locked = fields.Boolean(string='Pressetext kurz gesperrt', copy=False)
    artist_portal_long_locked = fields.Boolean(string='Pressetext lang gesperrt', copy=False)
    artist_portal_photo_locked = fields.Boolean(string='Pressefotos gesperrt', copy=False)
    artist_portal_graphics_locked = fields.Boolean(string='Grafik manuell bearbeitet', copy=False)
    artist_portal_media_ready = fields.Boolean(string='Pressetexte/Fotos vollständig', compute='_compute_artist_portal_media_ready')

    @api.depends('artist_portal_photo_ids', 'artist_portal_photo_ids.active',
                 'artist_portal_photo_ids.format', 'description')
    def _compute_artist_portal_media_ready(self):
        for event in self:
            has_photo = any(p.active for p in event.artist_portal_photo_ids)
            event.artist_portal_media_ready = bool(has_photo and html2plaintext(event[SHORT_FIELD] or '').strip()
                                            and html2plaintext(event.description or '').strip()) if SHORT_FIELD in event._fields else False

    def _is_artist_portal_upload_stage(self):
        self.ensure_one()
        return self._is_artist_portal_stage() or bool(self._artist_portal_stage_names() & {'gebucht', 'booked'})

    def _is_artist_portal_booked(self):
        self.ensure_one()
        return bool(self._artist_portal_stage_names() & {'gebucht', 'booked'})

    def _artist_portal_photo_image_field(self):
        self.ensure_one()
        for field in ('image_1920', 'image_1024'):
            if field in self._fields:
                return field
        return False

    def write(self, vals):
        # Do not lock a field just because a user opened the form: only actual changes count.
        if not self.env.context.get('artist_portal_source'):
            for event in self:
                locks = {}
                if SHORT_FIELD in vals and SHORT_FIELD in event._fields and vals[SHORT_FIELD] != event[SHORT_FIELD]:
                    locks['artist_portal_short_locked'] = True
                if 'description' in vals and vals['description'] != event.description:
                    locks['artist_portal_long_locked'] = True
                if any(name in vals and name in event._fields and vals[name] != event[name]
                       for name in ('image_1920', 'image_1024')):
                    locks['artist_portal_photo_locked'] = True
                if locks:
                    super(EventEvent, event.with_context(artist_portal_source=True)).write(locks)
        old_stage = {event.id: event._is_artist_portal_booked() for event in self} if 'stage_id' in vals else {}
        result = super().write(vals)
        if old_stage and not self.env.context.get('artist_portal_source'):
            for event in self:
                if not old_stage[event.id] and event._is_artist_portal_booked() and not event.artist_portal_invitation_sent_at:
                    try:
                        event._artist_portal_send_invitation()
                    except UserError as exc:
                        _logger.warning('Artist portal invitation not queued for event %s: %s', event.id, exc)
                        event.message_post(body=html.escape(str(exc)))
        return result

    def _artist_portal_staging(self):
        param = self.env['ir.config_parameter'].sudo().get_param('gl_event_artist_portal.test_mode')
        # Unknown environments fail closed: never send test traffic to external artists.
        stage = os.environ.get('ODOO_STAGE', '').lower()
        delivery = self.env['ir.config_parameter'].sudo().get_param('gl_event_artist_portal.delivery_mode')
        return stage in ('staging', 'dev', 'development', 'test') or param == '1' or not (stage == 'production' or delivery == 'production')

    def _artist_portal_send_invitation(self, force_test=False):
        self.ensure_one()
        if not self._is_artist_portal_upload_stage():
            raise UserError(_('Die Einladung ist erst ab der Phase „Gebucht“ möglich.'))
        if not self.artist_portal_access_token:
            self.with_context(artist_portal_source=True).write({'artist_portal_access_token': uuid.uuid4().hex})
        staging = self._artist_portal_staging()
        contact = self.artist_portal_contract_contact_id
        if not staging and not force_test and not (contact and contact.email):
            raise UserError(_('Bitte im Vertragskontakt eine gültige E-Mail-Adresse eintragen.'))
        recipient = 'julius@groundlift.de' if (staging or force_test) else contact.email
        link = '%s/event/artist/%s/%s' % (self.get_base_url().rstrip('/'), self.id, self.artist_portal_access_token)
        body = (self.artist_portal_introduction or '').replace('{event}', self.name or '').replace('{portal_url}', link)
        if '{portal_url}' not in (self.artist_portal_introduction or ''):
            body += '\n\n' + link
        label = '[STAGING TEST] ' if staging or force_test else ''
        mail = self.env['mail.mail'].sudo().create({
            'subject': '%sGROUNDLIFT: Künstler-/Agenturportal – %s' % (label, self.name),
            'body_html': '<div style="font-family:Arial,sans-serif;white-space:pre-line">%s</div>' % html.escape(body),
            'email_to': recipient,
            'email_from': self.company_id.email or self.env.user.email or 'info@groundlift.de',
            'reply_to': self.company_id.email or self.env.user.email or 'info@groundlift.de',
            'auto_delete': False,
        })
        if not force_test:
            self.with_context(artist_portal_source=True).write({
                'artist_portal_invitation_sent_at': fields.Datetime.now(),
                'artist_portal_invitation_recipient': recipient,
            })
        self.message_post(body=_('Portal-Einladung in E-Mail-Warteschlange an %s (Mail-ID %s).') % (recipient, mail.id))
        return mail

    def action_artist_portal_send_invitation(self):
        for event in self:
            event._artist_portal_send_invitation()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Künstlerportal'), 'message': _('Einladung in die E-Mail-Warteschlange gestellt.'),
            'type': 'success', 'sticky': False}}

    def action_artist_portal_send_test_mail(self):
        for event in self:
            event._artist_portal_send_invitation(force_test=True)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Künstlerportal'), 'message': _('Testmail an julius@groundlift.de in Warteschlange.'),
            'type': 'success', 'sticky': False}}

    def _artist_portal_photos_editable(self):
        self.ensure_one()
        if self.artist_portal_photo_locked or self.artist_portal_graphics_locked:
            return False
        posters = self.env['gl.graphics.poster'].sudo().search([
            ('event_id', '=', self.id), ('active', '=', True)])
        return not any(poster.last_rendered_at or poster.output_ids or
                       (not poster.artist_portal_seeded and
                        (poster.source_image or poster.editor_state)) for poster in posters)

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        """Place contract contact in the Studio tab when that optional tab exists.

        Studio creates its pages outside this add-on's source XML, so a static
        inherited-view xpath would cause installation failures on fresh DBs.
        """
        result = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type != 'form' or not result.get('arch'):
            return result
        root = etree.fromstring(result['arch'].encode('utf-8'))
        pages = root.xpath("//page[@string='Vertragsdaten' or @name='vertragsdaten' or @name='contract_data']")
        if pages and not pages[0].xpath(".//field[@name='artist_portal_contract_contact_id']"):
            group = etree.Element('group', string='Künstler-/Agenturportal')
            etree.SubElement(group, 'field', name='artist_portal_contract_contact_id')
            pages[0].insert(0, group)
            result['arch'] = etree.tostring(root, encoding='unicode')
        return result

    def _artist_portal_sync_graphics(self):
        """Seed the existing graphics editor; final Canvas render occurs in-browser."""
        for event in self:
            if event.artist_portal_graphics_locked:
                continue
            Poster = self.env['gl.graphics.poster'].sudo().with_context(artist_portal_source=True)
            poster = Poster.search([('event_id', '=', event.id), ('active', '=', True)],
                                   order='write_date desc, id desc', limit=1)
            photos = event.artist_portal_photo_ids.filtered('active')
            if not event.artist_portal_media_ready:
                # Removal of the last photo must not leave a stale image in a
                # draft poster that was previously seeded from the portal.
                if not photos and poster and poster.artist_portal_seeded and event._artist_portal_photos_editable():
                    poster.write({name: False for name in (
                        'source_image', 'design_element_square_image',
                        'design_element_scope_image', 'design_element_flat_image')})
                continue
            if not event._artist_portal_photos_editable():
                event.with_context(artist_portal_source=True).write({
                    'artist_portal_graphics_locked': True,
                    'artist_portal_photo_locked': True})
                continue
            square = photos.filtered(lambda p: p.format == 'square')[:1]
            landscape = photos.filtered(lambda p: p.format == 'landscape')[:1]
            portrait = photos.filtered(lambda p: p.format == 'portrait')[:1]
            base = landscape or square or portrait
            values = {
                'artist_portal_seeded': True,
                'source_image': base.image,
                'source_image_filename': base.filename,
                'summary_text': event[SHORT_FIELD] or '',
                'design_element_square_image': square.image if square else False,
                'design_element_square_filename': square.filename if square else False,
                'design_element_flat_image': landscape.image if landscape else False,
                'design_element_flat_filename': landscape.filename if landscape else False,
                'design_element_scope_image': landscape.image if landscape else False,
                'design_element_scope_filename': landscape.filename if landscape else False,
            }
            if poster:
                poster.write(values)
            else:
                Poster.create(dict(values, event_id=event.id))


class GraphicsPoster(models.Model):
    _inherit = 'gl.graphics.poster'

    artist_portal_seeded = fields.Boolean(string='Aus Künstlerportal vorbereitet', copy=False)

    def write(self, vals):
        tracked = set(vals) & {
            'source_image', 'design_element_square_image', 'design_element_scope_image',
            'design_element_flat_image', 'editor_state', 'summary_text', 'event_title',
            'event_subtitle', 'color_1', 'color_2', 'claim', 'photo_credit', 'output_image',
            'date_text', 'time_text', 'sticker_mode', 'sticker_text', 'sticker_color',
            'ticket_link_text', 'ticket_url', 'qr_url', 'admission_time_text', 'ticket_price_text',
        }
        to_lock = self.env['event.event']
        if tracked and not self.env.context.get('artist_portal_source'):
            for poster in self:
                if poster.event_id and any(name in poster._fields and vals[name] != poster[name] for name in tracked):
                    to_lock |= poster.event_id
        result = super().write(vals)
        for event in to_lock:
            event.with_context(artist_portal_source=True).write({
                'artist_portal_graphics_locked': True, 'artist_portal_photo_locked': True})
        return result
