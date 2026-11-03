# -*- coding: utf-8 -*-
"""Artist self-service documents, media, locks and invitation mail."""
import html
import logging
import os
import uuid
from lxml import etree
from markupsafe import Markup, escape
from urllib.parse import urlsplit

from odoo import _, api, fields, models
from odoo.tools import html2plaintext
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

SHORT_FIELD = 'x_studio_event_kurzbeschreibung'
RIDER_FIELDS = {'tech': 'x_studio_tech_rider', 'hospitality': 'x_studio_hospitality_rider'}
MAX_IMAGE = 12 * 1024 * 1024
MAX_DOCUMENT = 20 * 1024 * 1024


DEFAULT_INVITATION_TEXT = (
    'Liebe Künstlerinnen, Künstler und Agenturen,\n\n'
    'für die Veranstaltung {event} steht euch unser Groundlift-Portal zur Verfügung. '
    'Dort könnt ihr Tech- und Hospitality-Rider, Pressefotos und Pressetexte einreichen. '
    'Ab der Phase „Angekündigt“ könnt ihr außerdem die Gästeliste pflegen und Ticketstände ansehen.\n\n'
    'Euer persönlicher Link: {portal_url}\n\nViele Grüße\nEuer GROUNDLIFT-Team'
)
INTRODUCTION_PARAMETER = 'gl_event_artist_portal.default_introduction'
TECH_USER_PARAMETER = 'gl_event_artist_portal.default_technical_user_id'
SERVICE_USER_PARAMETER = 'gl_event_artist_portal.default_service_user_id'


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

    # Important: existing event.event rows get False when the module is upgraded.
    # New rows are explicitly opted in by create(), irrespective of their event date.
    # Never use default=True: that would also upgrade old events to the new portal.
    artist_portal_extended_enabled = fields.Boolean(
        string='Erweitertes Künstlerportal für diese Veranstaltung',
        default=False, copy=False, readonly=True,
        help='Nur Veranstaltungen, die nach diesem Update angelegt wurden, '
             'erhalten Rider-, Presse-, Grafik- und Einladungsfunktionen.')

    # 'default' keeps historic events in guestlist-only mode, while events
    # created with the extended portal automatically have all four sections.
    # Explicit show/hide permits precise per-event overrides without migrations
    # or bulk updates to any existing event.
    _PORTAL_SECTION_OPTIONS = [
        ('default', 'Standard (Bestand: aus / neu: an)'),
        ('show', 'Anzeigen'),
        ('hide', 'Ausblenden'),
    ]
    artist_portal_section_photos = fields.Selection(
        _PORTAL_SECTION_OPTIONS, string='Bilder', default='default', copy=False)
    artist_portal_section_press = fields.Selection(
        _PORTAL_SECTION_OPTIONS, string='Pressetext', default='default', copy=False)
    artist_portal_section_tech = fields.Selection(
        _PORTAL_SECTION_OPTIONS, string='Technical Rider', default='default', copy=False)
    artist_portal_section_hospitality = fields.Selection(
        _PORTAL_SECTION_OPTIONS, string='Hospitality Rider', default='default', copy=False)
    # These two sections were already enabled for ALL events in their respective
    # stages, including pre-existing events. Their defaults must preserve that.
    _STANDARD_VISIBLE_OPTIONS = [
        ('default', 'Standard (in der passenden Phase: an)'),
        ('show', 'Anzeigen'),
        ('hide', 'Ausblenden'),
    ]
    artist_portal_section_video = fields.Selection(
        _STANDARD_VISIBLE_OPTIONS, string='Live bei Groundlift', default='default', copy=False)
    artist_portal_section_gema = fields.Selection(
        _STANDARD_VISIBLE_OPTIONS, string='GEMA', default='default', copy=False)
    artist_portal_gema_url = fields.Char(
        string='GEMA-Link für Künstler/Agentur', copy=False,
        help='Ab Phase Abrechnung (auch Beendet) im Künstlerportal sichtbar. Vollständige https://-Adresse eintragen.')

    def _artist_portal_section_enabled(self, section):
        self.ensure_one()
        name = {
            'photos': 'artist_portal_section_photos',
            'press': 'artist_portal_section_press',
            'tech': 'artist_portal_section_tech',
            'hospitality': 'artist_portal_section_hospitality',
            'video': 'artist_portal_section_video',
            'gema': 'artist_portal_section_gema',
        }.get(section)
        if not name:
            return False
        setting = self[name] or 'default'
        if setting == 'hide':
            return False
        if section in ('video', 'gema'):
            # Before this update both were visible by default on historic AND
            # new events. 'show' and 'default' preserve that behavior.
            return True
        return setting == 'show' or (setting == 'default' and bool(self.artist_portal_extended_enabled))

    def _artist_portal_any_media_enabled(self):
        self.ensure_one()
        return any(self._artist_portal_section_enabled(key)
                   for key in ('photos', 'press', 'tech', 'hospitality'))

    def _is_artist_portal_media_stage(self):
        """Only Gebucht accepts press or rider uploads, including older opt-in events.

        A legacy event may enable any of the four areas individually. Neither
        Angekündigt nor Abrechnung may expose an old upload form or POST route.
        """
        self.ensure_one()
        return bool(self._artist_portal_any_media_enabled() and self._is_artist_portal_booked())

    def _is_artist_portal_accounting_stage(self):
        self.ensure_one()
        return bool(self._artist_portal_section_enabled('gema') and
                    self._artist_portal_stage_names() & {
                        'abrechnung', 'beendet', 'billing', 'invoicing',
                        'done', 'finished',
                    })

    def _artist_portal_valid_gema_url(self):
        self.ensure_one()
        raw = (self.artist_portal_gema_url or '').strip()
        if not raw or any(ch in raw for ch in ('\r', '\n', '\t', ' ')):
            return False
        try:
            parts = urlsplit(raw)
            return raw if parts.scheme in ('https', 'http') and parts.netloc and not parts.username and not parts.password else False
        except ValueError:
            return False

    @api.model
    def _artist_portal_default_staff_value(self, field_name, user_id):
        """Translate a configured internal Odoo user to the existing Studio field.

        Studio may define the recipient as a user, contact or HR employee.
        Never write an incompatible foreign key or change an existing event.
        """
        studio_field = self._fields.get(field_name)
        if not studio_field or not user_id:
            return None
        try:
            user = self.env['res.users'].sudo().browse(int(user_id)).exists()
        except (TypeError, ValueError):
            _logger.warning('Invalid default artist-portal user id for %s: %r', field_name, user_id)
            return None
        if not user or not user.active or user.share:
            _logger.warning('Configured artist-portal user for %s is not an active internal user', field_name)
            return None
        comodel = getattr(studio_field, 'comodel_name', None)
        if comodel == 'res.users':
            targets = user.ids
        elif comodel == 'res.partner':
            targets = user.partner_id.ids
        elif comodel == 'hr.employee':
            employees = self.env['hr.employee'].sudo().search(
                [('user_id', '=', user.id)], order='id asc')
            targets = employees.ids[:1]
        else:
            _logger.warning('Unsupported Studio staff field %s (%s / %s)',
                            field_name, studio_field.type, comodel)
            return None
        if not targets:
            _logger.warning('No matching %s found for default artist-portal user %s', field_name, user.id)
            return None
        if studio_field.type == 'many2one':
            return targets[0]
        if studio_field.type == 'many2many':
            return [(6, 0, targets)]
        _logger.warning('Unsupported relation type for artist-portal staff field %s: %s',
                        field_name, studio_field.type)
        return None

    @api.model
    def _artist_portal_new_event_defaults(self):
        params = self.env['ir.config_parameter'].sudo()
        return {
            'artist_portal_introduction': params.get_param(
                INTRODUCTION_PARAMETER, default=DEFAULT_INVITATION_TEXT),
            'x_studio_techn_leitung': self._artist_portal_default_staff_value(
                'x_studio_techn_leitung', params.get_param(TECH_USER_PARAMETER)),
            'x_studio_organisation_service': self._artist_portal_default_staff_value(
                'x_studio_organisation_service', params.get_param(SERVICE_USER_PARAMETER)),
        }

    @api.model
    def default_get(self, fields_list):
        """Show the defaults in the Odoo new-event form before it is saved."""
        values = super().default_get(fields_list)
        for name, value in self._artist_portal_new_event_defaults().items():
            if (name in fields_list and name in self._fields
                    and 'default_' + name not in self.env.context and value is not None):
                values[name] = value
        return values

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self._artist_portal_new_event_defaults()
        prepared = []
        for vals in vals_list:
            # Existing records never pass create(); old events remain in the
            # original guestlist-only mode. New ones explicitly opt in.
            values = dict(vals, artist_portal_extended_enabled=True)
            for name, value in defaults.items():
                # Studio fields are optional, and event-specific values (including
                # an intentional False) must take precedence over global defaults.
                if name in self._fields and name not in values and value is not None:
                    values[name] = value
            prepared.append(values)
        return super().create(prepared)

    artist_portal_contract_contact_id = fields.Many2one(
        'res.partner', string='Vertrag: Künstler / Agentur (Portal-Einladung)', copy=False,
        help='Die Einladung geht an die E-Mail-Adresse dieses Kontakts. Im Staging nur an julius@groundlift.de.')
    artist_portal_introduction = fields.Text(
        string='Einladungstext Künstler-/Agenturportal', copy=False,
        help='Bei Erstellung mit dem globalen Standard vorbelegt; anschließend je Veranstaltung individuell änderbar.')
    artist_portal_invitation_sent_at = fields.Datetime(string='Portal-Einladung versendet', readonly=True, copy=False)
    artist_portal_invitation_recipient = fields.Char(string='Letzter Einladungsempfänger', readonly=True, copy=False)
    artist_portal_photo_ids = fields.One2many('gl.artist.portal.photo', 'event_id', string='Pressefotos')
    # The Odoo event description can be prefilled by an event template; it is NOT
    # an artist-submitted press text. Keep the original separate and untouched
    # until an artist actually submits text here.
    artist_portal_press_long = fields.Text(string='Vom Künstler eingereichter Langtext', copy=False)
    artist_portal_press_submitted_at = fields.Datetime(string='Presseangaben zuletzt eingereicht', copy=False)
    artist_portal_contact_last_sent_at = fields.Datetime(
        string='Letzte Portal-Anfrage zur Videoaufzeichnung', copy=False, readonly=True)
    artist_portal_notifications_enabled = fields.Boolean(
        string='Odoo-Benachrichtigungen für Portal-Uploads', default=True, copy=False)

    artist_portal_short_locked = fields.Boolean(string='Pressetext kurz gesperrt', copy=False)
    artist_portal_long_locked = fields.Boolean(string='Pressetext lang gesperrt', copy=False)
    artist_portal_photo_locked = fields.Boolean(string='Pressefotos gesperrt', copy=False)
    artist_portal_graphics_locked = fields.Boolean(string='Grafik manuell bearbeitet', copy=False)
    artist_portal_media_ready = fields.Boolean(string='Pressetexte/Fotos vollständig', compute='_compute_artist_portal_media_ready')

    @api.depends('artist_portal_photo_ids', 'artist_portal_photo_ids.active',
                 'artist_portal_photo_ids.format', 'artist_portal_press_long', 'description')
    def _compute_artist_portal_media_ready(self):
        for event in self:
            has_photo = any(p.active for p in event.artist_portal_photo_ids)
            # A prefilled Odoo event description is not artist press material.
            event.artist_portal_media_ready = bool(
                has_photo and event.artist_portal_press_long and event.artist_portal_press_long.strip()
                and html2plaintext(event[SHORT_FIELD] or '').strip()
            ) if SHORT_FIELD in event._fields else False

    def _artist_portal_notify_users(self, source_field):
        """Only resolve actual internal Odoo accounts, never arbitrary contact emails."""
        self.ensure_one()
        if source_field not in self._fields:
            _logger.warning('Artist portal notification: missing field %s on event %s', source_field, self.id)
            return self.env['res.users']
        value = self[source_field]
        users = self.env['res.users']
        if not value:
            return users
        if not hasattr(value, '_name'):
            _logger.warning('Artist portal notification: %s is not a relational user field', source_field)
            return users
        if value._name == 'res.users':
            users = value
        elif value._name == 'res.partner':
            users = self.env['res.users'].sudo().search([('partner_id', 'in', value.ids), ('share', '=', False)])
        elif value._name == 'hr.employee':
            users = value.mapped('user_id')
        else:
            _logger.warning('Artist portal notification: unsupported recipient model %s for %s',
                            value._name, source_field)
        return users.sudo().filtered(lambda user: user.active and not user.share and user.partner_id)

    def _artist_portal_notify(self, source_field, title, details):
        """Persist an Odoo Discuss inbox item plus the existing event To-do."""
        self.ensure_one()
        if not self.artist_portal_notifications_enabled:
            return
        users = self._artist_portal_notify_users(source_field)
        if not users:
            _logger.info('Artist portal: no internal recipient for %s on event %s', source_field, self.id)
            return
        message = '%s: %s' % (self.name or _('Veranstaltung'), details)
        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        model_id = self.env['ir.model']._get_id('event.event')
        # Odoo 19 Discuss: persist a user_notification and deliver it through
        # mail.message/inbox. Do not emit 'simple_notification' (top-right toast).
        # Force inbox for these internal recipients even if their personal
        # notification preference would normally choose email; no SMTP is used.
        try:
            with self.env.cr.savepoint():
                partner_ids = users.mapped('partner_id').ids
                author = self.env.ref('base.partner_root', raise_if_not_found=False)
                if not author:
                    author = self.env.user.partner_id
                safe_body = Markup('<p>%s</p>') % escape(message)
                inbox_message = self.sudo()._message_create([{
                    'model': 'event.event', 'res_id': self.id,
                    'message_type': 'user_notification',
                    'subtype_id': self.env.ref('mail.mt_note').id,
                    'subject': title,
                    'body': safe_body,
                    'is_internal': True,
                    'author_id': author.id,
                    'partner_ids': partner_ids,
                    'email_add_signature': False,
                }])
                recipients = [{'id': user.partner_id.id, 'uid': user.id, 'notif': 'inbox'}
                              for user in users]
                self.sudo()._notify_thread_by_inbox(inbox_message, recipients)
        except Exception:
            _logger.exception('Could not add artist-portal Discuss inbox notification for event %s', self.id)
        # Keep the durable event-specific To-do activity from earlier versions.
        for user in users:
            try:
                with self.env.cr.savepoint():
                    if activity_type and model_id:
                        self.env['mail.activity'].sudo().create({
                            'res_model_id': model_id,
                            'res_id': self.id,
                            'activity_type_id': activity_type.id,
                            'user_id': user.id,
                            'summary': title,
                            'note': html.escape(message),
                            'date_deadline': fields.Date.context_today(self),
                        })
            except Exception:
                _logger.exception('Could not add artist-portal To-do for event %s, user %s',
                                  self.id, user.id)

    def _is_artist_portal_upload_stage(self):
        self.ensure_one()
        return bool(self.artist_portal_extended_enabled and (
            self._is_artist_portal_stage() or
            self._artist_portal_stage_names() & {'gebucht', 'booked'}))

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
            for event in self.filtered('artist_portal_extended_enabled'):
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
                if (event.artist_portal_extended_enabled and not old_stage[event.id]
                        and event._is_artist_portal_booked() and not event.artist_portal_invitation_sent_at):
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
        if not self.artist_portal_extended_enabled:
            raise UserError(_('Bestehende Veranstaltungen verwenden ausschließlich das bisherige Gästelistenportal.'))
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
        if not self._artist_portal_section_enabled('photos') or self.artist_portal_photo_locked or self.artist_portal_graphics_locked:
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
            if (not event._artist_portal_section_enabled('photos')
                    or not event._artist_portal_section_enabled('press')
                    or event.artist_portal_graphics_locked):
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
            # Use the square press image as the primary/default source image for the
            # graphics editor. This ensures the artist portal's 1:1 upload is what
            # initially appears in the Grafik-App and aligns with the POS image.
            # The dedicated per-format design images remain filled separately below.
            base = square or landscape or portrait
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
                if (poster.event_id and poster.event_id.artist_portal_extended_enabled
                        and any(name in poster._fields and vals[name] != poster[name] for name in tracked)):
                    to_lock |= poster.event_id
        result = super().write(vals)
        for event in to_lock:
            event.with_context(artist_portal_source=True).write({
                'artist_portal_graphics_locked': True, 'artist_portal_photo_locked': True})
        return result
