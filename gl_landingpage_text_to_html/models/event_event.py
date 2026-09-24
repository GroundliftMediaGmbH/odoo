"""Website HTML bridge for Groundlift events.

Keep the original Studio text field's name, type and value semantics intact.
Keep gl_landingpage_html from v1; connect it to Odoo's standard event.description
HTML field only where it is safe (or when an editor explicitly opts in).
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .conversion import html_to_plain, plain_to_html

_logger = logging.getLogger(__name__)
PARAMETER = 'gl_landingpage_text_to_html.source_field'
SKIP_SYNC = 'gl_text_to_html_skip_sync'


class EventEvent(models.Model):
    _inherit = 'event.event'

    gl_landingpage_html = fields.Html(
        string='Landingpage Beschreibung (HTML)',
        sanitize=True,
        translate=False,
        copy=False,
        help='Formatierter Text. Bei Änderungen wird das ursprüngliche Studio-Textfeld als Klartext aktualisiert.',
    )
    gl_landingpage_native_linked = fields.Boolean(
        string='Mit Odoo-Webseitenbeschreibung verbunden', copy=False,
        help='Wenn aktiv, sind Landingpage HTML und die native Odoo-Eventbeschreibung synchron.',
    )
    gl_landingpage_native_backup = fields.Html(
        string='Sicherung der vorherigen Odoo-Webseitenbeschreibung',
        sanitize=True, translate=False, copy=False,
        groups='base.group_system',
    )

    @api.model
    def _gl_get_plain_field_name(self):
        configured = self.env['ir.config_parameter'].sudo().get_param(PARAMETER, '').strip()
        if configured:
            field = self._fields.get(configured)
            if field and field.type == 'text' and configured != 'description':
                return configured
            _logger.warning('Landingpage Text_to_HTML: invalid source field %r.', configured)
            return None
        hits = [
            name for name, field in self._fields.items()
            if field.type == 'text'
            and field.string.strip().casefold() in ('event beschreibung', 'eventbeschreibung')
        ]
        if len(hits) == 1:
            return hits[0]
        _logger.warning(
            'Landingpage Text_to_HTML: source field ambiguous; set %s (matches: %s).',
            PARAMETER, hits,
        )
        return None

    def _gl_internal_write(self, vals):
        """Bypass only our own sync logic; retain other addon write overrides."""
        return self.with_context(**{SKIP_SYNC: True}).write(vals)

    def _gl_fill_html_from_plain(self):
        source = self._gl_get_plain_field_name()
        for event in self:
            if source and not event.gl_landingpage_html and event[source]:
                event._gl_internal_write({'gl_landingpage_html': plain_to_html(event[source])})

    def _gl_link_native_if_safe(self):
        """Do not overwrite an unrelated existing standard Odoo description.

        Safe when empty or semantically equal to our new HTML's plain text;
        already-linked events are of course kept synchronized.
        """
        for event in self:
            if not event.gl_landingpage_html:
                continue
            native = event.description or ''
            replacement = event.gl_landingpage_html
            native_same = html_to_plain(native).strip() == html_to_plain(replacement).strip()
            if event.gl_landingpage_native_linked or not native or native_same:
                vals = {'gl_landingpage_native_linked': True}
                if native != replacement:
                    vals['description'] = replacement
                event._gl_internal_write(vals)
            else:
                _logger.info(
                    'Landingpage Text_to_HTML: event %s has an independent Odoo description; '
                    'use action_gl_force_native_link to replace it explicitly.', event.id,
                )

    def action_gl_copy_plain_to_html(self):
        if not self._gl_get_plain_field_name():
            raise UserError(_(
                'Quellfeld nicht erkannt. Den Systemparameter '
                'gl_landingpage_text_to_html.source_field auf den technischen Namen '
                'des bisherigen event.event-Textfelds setzen.'
            ))
        self._gl_fill_html_from_plain()
        self._gl_link_native_if_safe()
        return True

    def action_gl_sync_native_if_safe(self):
        self._gl_fill_html_from_plain()
        self._gl_link_native_if_safe()
        return True

    def action_gl_force_native_link(self):
        """Explicitly replace an unrelated native Odoo website description.

        Make a recoverable copy once, never silently discard it during migration.
        """
        for event in self:
            if not event.gl_landingpage_html:
                event._gl_fill_html_from_plain()
            if not event.gl_landingpage_html:
                raise UserError(_('Bitte zuerst eine Landingpage-HTML-Beschreibung eintragen.'))
            vals = {
                'description': event.gl_landingpage_html,
                'gl_landingpage_native_linked': True,
            }
            if (not event.gl_landingpage_native_backup
                    and event.description
                    and event.description != event.gl_landingpage_html):
                vals['gl_landingpage_native_backup'] = event.description
            event._gl_internal_write(vals)
        return True

    @api.model
    def _gl_migrate_existing(self):
        """Called on module upgrade, not just the initial installation."""
        events = self.sudo()
        if not events._gl_get_plain_field_name():
            return
        last_id = 0
        while True:
            batch = events.search([('id', '>', last_id)], order='id', limit=200)
            if not batch:
                break
            batch._gl_fill_html_from_plain()
            batch._gl_link_native_if_safe()
            last_id = batch[-1].id

    @api.model_create_multi
    def create(self, vals_list):
        events = super().create(vals_list)
        if self.env.context.get(SKIP_SYNC):
            return events
        source = self._gl_get_plain_field_name()
        if not source:
            return events
        for event, vals in zip(events, vals_list):
            if 'gl_landingpage_html' in vals:
                event._gl_internal_write({source: html_to_plain(event.gl_landingpage_html)})
            elif event[source] and not event.gl_landingpage_html:
                event._gl_fill_html_from_plain()
            event._gl_link_native_if_safe()
        return events

    def write(self, vals):
        if self.env.context.get(SKIP_SYNC):
            return super().write(vals)
        source = self._gl_get_plain_field_name()
        if not source:
            return super().write(vals)
        editing_html = 'gl_landingpage_html' in vals
        editing_plain = source in vals
        editing_native = 'description' in vals
        if not (editing_html or editing_plain or editing_native):
            return super().write(vals)

        # Link only if the NATIVE description matched the PREVIOUS content.
        # Waiting until after super().write() would make a legitimate first
        # HTML edit appear different, incorrectly preventing safe linking.
        if editing_html or editing_plain:
            for event in self:
                if event.gl_landingpage_native_linked:
                    continue
                previous = event.gl_landingpage_html or plain_to_html(event[source])
                native = event.description or ''
                if not native or html_to_plain(native).strip() == html_to_plain(previous).strip():
                    event._gl_internal_write({'gl_landingpage_native_linked': True})

        # Existing historical behavior: entering the plain-text field regenerates
        # HTML, unless HTML was explicitly submitted in the same write.
        vals = dict(vals)
        if editing_plain and not editing_html:
            vals['gl_landingpage_html'] = plain_to_html(vals[source])
        # A genuine website edit of native description is the third entry point.
        # Only regard it as ours when the native field was already linked.
        result = super().write(vals)
        for event in self:
            if editing_html or editing_plain:
                if editing_html:
                    text = html_to_plain(event.gl_landingpage_html)
                    if event[source] != text:
                        event._gl_internal_write({source: text})
                event._gl_link_native_if_safe()
            elif editing_native and event.gl_landingpage_native_linked:
                native_html = event.description or ''
                text = html_to_plain(native_html)
                updates = {}
                if event.gl_landingpage_html != native_html:
                    updates['gl_landingpage_html'] = native_html
                if event[source] != text:
                    updates[source] = text
                if updates:
                    event._gl_internal_write(updates)
        return result
